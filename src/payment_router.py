# src/payment_router.py
from __future__ import annotations

import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
import stripe


from src.ledger_db_access import get_payment_db
from src.secrets import get_secret
from src.login_logic import get_user
from src.css.utils import load_css

payment_router = APIRouter()

# ---- Secrets / config
STRIPE_SECRET_KEY = get_secret("STRIPE_SECRET_KEY")
stripe.api_key    = STRIPE_SECRET_KEY
CREDITS_PER_CENT  = int((get_secret("CREDITS_PER_CENT", default="1") or "1"))

# Optional: package-specific price IDs and credit grants
STRIPE_PRICE_ID_STARTER = get_secret("STRIPE_PRICE_ID_STARTER", default="")  # 5€
STRIPE_PRICE_ID_MEDIUM   = get_secret("STRIPE_PRICE_ID_MEDIUM", default="")    # 20€
STRIPE_PRICE_ID_PRO     = get_secret("STRIPE_PRICE_ID_PRO", default="")      # 100€

# Control credit grant per package here (independent of amount_cents)
PACKAGES: dict[str, dict] = {
    "starter": {"price_id": STRIPE_PRICE_ID_STARTER, "credits": 50},
    "value":   {"price_id": STRIPE_PRICE_ID_MEDIUM,   "credits": 500},
    "pro":     {"price_id": STRIPE_PRICE_ID_PRO,     "credits": 5000},
}

def get_stripe_webhook_secret() -> str:
    return get_secret("STRIPE_WEBHOOK_SECRET")

log = logging.getLogger("stripe_webhooks")



@payment_router.get("/header/credits", response_class=HTMLResponse)
def header_credits(request: Request, db: Session = Depends(get_payment_db)):
    user = (request.session or {}).get("user") or {}
    sub = (user or {}).get("sub")

    balance = 0
    if sub:
        row = db.execute(
            text("""
                SELECT ub.balance
                FROM app_user u
                LEFT JOIN user_balance ub ON ub.user_id = u.id
                WHERE u.oauth_sub = :sub
            """),
            {"sub": sub},
        ).first()
        balance = int(row[0]) if row and row[0] is not None else 0

    css = load_css("credits.css")
    css_block = f"<style>\n{css}\n</style>"

    # IMPORTANT: this iframe never fetches; it only accepts set-balance pushes.
    html = f"""<!doctype html>
                <html><head><meta charset="utf-8">
                <meta http-equiv="Cache-Control" content="no-store" />
                {css_block}
                </head><body>
                <div class="credits-wrap">
                    <span class="pill"><span class="icon" aria-hidden="true">💳</span> Credits: <strong id="val">{balance}</strong></span>
                    <a class="buybtn" href="/buy" target="_top" title="Buy more credits" aria-label="Buy more credits"></a>
                </div>
                <script>
                (() => {{
                  const el = document.getElementById('val');
                  const set = (v) => {{ if (el) el.textContent = String(v); }};
                  // Only react to parent messages; do not fetch from here.
                  window.addEventListener('message', (ev) => {{
                    try {{
                      const d = ev?.data;
                      if (d && d.type === 'set-balance' && Number.isFinite(+d.balance)) {{
                        set(d.balance);
                      }}
                    }} catch {{}}
                  }}, false);
                }})();
                </script>
                </body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})



### 1. Redirect to stripe payment system ###
@payment_router.post("/payments/create-checkout-session")
async def create_checkout_session(request: Request):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    user  = request.session.get("user") or {}
    email = user.get("email")
    sub   = user.get("sub")

    # Required JSON body: { package: 'starter'|'value'|'pro' }
    try:
        data = await request.json()
    except Exception:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("package"), str):
        raise HTTPException(status_code=400, detail="Missing package")

    package = data["package"].strip().lower()
    pkg = PACKAGES.get(package)
    if not pkg or not pkg.get("price_id"):
        raise HTTPException(status_code=400, detail="Unknown or unconfigured package")

    credits_grant = int(pkg.get("credits") or 0)
    metadata = {"user_sub": sub or "", "package": package, "credits_grant": str(credits_grant)}

    origin = f"{request.url.scheme}://{request.url.netloc}"
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": pkg["price_id"], "quantity": 1}],
            success_url=f"{origin}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/checkout/cancel",
            customer_email=email,
            allow_promotion_codes=True,
            billing_address_collection="auto",
            client_reference_id=sub,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
        )
        return JSONResponse({"url": session.url})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _credit_purchase(
    db: Session, *,
    user_sub: str,
    payment_intent: str,
    amount_cents: int,
    event_id: str,
    credits_override: int | None = None,
):
    if not user_sub or not payment_intent or amount_cents <= 0:
        return {"ok": False, "reason": "missing_fields_or_zero"}

    credits = int(credits_override) if (credits_override and credits_override > 0) else (amount_cents * CREDITS_PER_CENT)

    with db.begin():
        user_id = db.execute(
            text("""
            INSERT INTO app_user(oauth_sub) VALUES (:sub)
            ON CONFLICT(oauth_sub) DO UPDATE SET oauth_sub=EXCLUDED.oauth_sub
            RETURNING id
            """),
            {"sub": user_sub},
        ).scalar_one()

        inserted = db.execute(
            text("""
            INSERT INTO payment(provider, provider_event_id, user_id, amount_cents, credits_granted, status)
            VALUES ('stripe', :pi, :uid, :amt, :credits, 'succeeded')
            ON CONFLICT(provider_event_id) DO NOTHING
            RETURNING 1
            """),
            {"pi": payment_intent, "uid": user_id, "amt": amount_cents, "credits": credits},
        ).scalar_one_or_none()

        if not inserted:
            return {"ok": True, "dup": True, "payment_intent": payment_intent}

        db.execute(
            text("""
            INSERT INTO credit_ledger(user_id, delta, reason, source_type, source_id)
            VALUES (:uid, :delta, 'purchase', 'stripe_event', :eid)
            ON CONFLICT(source_type, source_id) DO NOTHING
            """),
            {"uid": user_id, "delta": credits, "eid": event_id},
        )

        db.execute(
            text("""
            INSERT INTO user_balance(user_id, balance) VALUES (:uid, :credits)
            ON CONFLICT(user_id) DO UPDATE SET balance = user_balance.balance + EXCLUDED.balance
            """),
            {"uid": user_id, "credits": credits},
        )

    return {"ok": True, "granted": credits, "payment_intent": payment_intent}


### 2. Stripe webhook ###
@payment_router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_payment_db)):
    raw = await request.body()
    payload = raw.decode("utf-8")
    sig = request.headers.get("Stripe-Signature")
    if not sig:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature")

    secret = get_stripe_webhook_secret()
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=secret)
    except Exception as e:
        log.warning("Invalid signature", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    etype = event["type"]
    data = event["data"]["object"]

    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session_id = data["id"]
        payment_intent = data.get("payment_intent")
        amount_total = int(data.get("amount_total") or 0)
        user_sub = (data.get("client_reference_id") or (data.get("metadata") or {}).get("user_sub"))
        meta = (data.get("metadata") or {})
        credits_override = None
        try:
            if "credits_grant" in meta:
                credits_override = int(meta.get("credits_grant") or 0)
        except Exception:
            credits_override = None

        res = _credit_purchase(
            db,
            user_sub=user_sub or "",
            payment_intent=payment_intent or "",
            amount_cents=amount_total,
            event_id=event["id"],
            credits_override=credits_override,
        )
        log.info("Checkout session success", extra={"evt": event["id"], "type": etype, "res": res})
        return JSONResponse({"ok": True, **res})

    if etype == "payment_intent.succeeded":
        pi = data
        payment_intent = pi["id"]
        amount_cents = int(pi.get("amount_received") or pi.get("amount") or 0)
        user_sub = (pi.get("metadata") or {}).get("user_sub") or ""
        meta = (pi.get("metadata") or {})
        credits_override = None
        try:
            if "credits_grant" in meta:
                credits_override = int(meta.get("credits_grant") or 0)
        except Exception:
            credits_override = None

        res = _credit_purchase(
            db,
            user_sub=user_sub,
            payment_intent=payment_intent,
            amount_cents=amount_cents,
            event_id=event["id"],
            credits_override=credits_override,
        )
        log.info("PI succeeded", extra={"evt": event["id"], "type": etype, "res": res})
        return JSONResponse({"ok": True, **res})

    if etype in ("charge.refunded", "charge.dispute.created"):
        charge = data
        payment_intent = charge.get("payment_intent")
        if not payment_intent:
            raise HTTPException(status_code=400, detail="Missing payment_intent on charge")

        if etype == "charge.refunded":
            amount_cents = int(charge.get("amount_refunded") or 0)
            reason = "refund"
            new_status = "refunded"
        else:
            amount_cents = int(charge.get("amount") or 0)
            reason = "chargeback"
            new_status = "disputed"

        credits = amount_cents * CREDITS_PER_CENT
        if credits <= 0:
            log.info("Negative adj noop", extra={"evt": event["id"], "type": etype})
            return JSONResponse({"ok": True, "noop": True})

        from sqlalchemy import text
        with db.begin():
            row = db.execute(
                text("SELECT user_id FROM payment WHERE provider_event_id=:pi"),
                {"pi": payment_intent},
            ).first()
            if not row:
                log.info("Negative adj ignored (unknown PI)", extra={"evt": event["id"], "type": etype})
                return JSONResponse({"ok": True, "ignored": True})

            user_id = row[0]
            db.execute(
                text("""
                INSERT INTO credit_ledger(user_id, delta, reason, source_type, source_id)
                VALUES (:uid, :neg, :reason, 'stripe_event', :eid)
                ON CONFLICT(source_type, source_id) DO NOTHING
                """),
                {"uid": user_id, "neg": -credits, "reason": reason, "eid": event["id"]},
            )
            db.execute(
                text("UPDATE user_balance SET balance = balance - :c WHERE user_id = :uid"),
                {"uid": user_id, "c": credits},
            )
            db.execute(
                text("UPDATE payment SET status=:st WHERE provider_event_id=:pi"),
                {"st": new_status, "pi": payment_intent},
            )

        log.info("Negative adj applied", extra={"evt": event["id"], "type": etype, "debited": credits})
        return JSONResponse({"ok": True, "type": etype, "debited": credits})

    log.info("Event ignored", extra={"evt": event["id"], "type": etype})
    return JSONResponse({"ok": True, "ignored": etype})


@payment_router.get("/checkout/success", response_class=HTMLResponse)
def checkout_success(
    request: Request,
    session_id: str | None = None,
    db: Session = Depends(get_payment_db),
):
    """
    Success landing page. Also verifies the Stripe session server-side and grants
    credits idempotently as a fallback in case webhooks are not delivered.
    """
    # Best-effort server-side verification/crediting
    if session_id:
        try:
            sess = stripe.checkout.Session.retrieve(session_id)
            payment_status = (sess or {}).get("payment_status")
            if payment_status == "paid":
                amount_total = int((sess or {}).get("amount_total") or 0)
                user_sub = (sess.get("client_reference_id") or (sess.get("metadata") or {}).get("user_sub") or "")
                # payment_intent may be an ID or an object
                pi = sess.get("payment_intent")
                payment_intent = (pi.get("id") if isinstance(pi, dict) else str(pi or ""))
                credits_override = None
                try:
                    meta = (sess.get("metadata") or {})
                    if "credits_grant" in meta:
                        credits_override = int(meta.get("credits_grant") or 0)
                except Exception:
                    credits_override = None

                if payment_intent and amount_total > 0 and user_sub:
                    res = _credit_purchase(
                        db,
                        user_sub=user_sub,
                        payment_intent=payment_intent,
                        amount_cents=amount_total,
                        event_id=sess.get("id") or session_id,
                        credits_override=credits_override,
                    )
                    log.info("Checkout success verified+credited", extra={"sid": session_id, "res": res})
                else:
                    log.info("Checkout success missing fields", extra={
                        "sid": session_id,
                        "user_sub": bool(user_sub),
                        "pi": bool(payment_intent),
                        "amt": amount_total,
                    })
            else:
                log.info("Checkout success not paid yet", extra={"sid": session_id, "status": payment_status})
        except Exception as e:
            log.warning("Checkout success verify failed", extra={"sid": session_id, "error": str(e)})

    # Push the fresh balance directly; tag the request for logging.
    return """
    <html><body style=\"font-family:system-ui\">
    <h2>✅ Payment successful</h2>
    <p>Thanks! Your purchase is complete.</p>
    <p><a href=\"/app/\">Go to Dashboard</a></p>
    <script>
      (async () => {
        try {
          const r = await fetch('/user/balance?src=checkout_success', { cache: 'no-store' });
          if (!r.ok) return;
          const j = await r.json();
          (window.opener || window.parent)?.postMessage(
            { type: 'set-balance', balance: j.balance ?? 0 },
            window.location.origin
          );
        } catch {}
      })();
    </script>
    </body></html>
    """

@payment_router.get("/checkout/cancel", response_class=HTMLResponse)
def checkout_cancel():
    return """
    <html><body style="font-family:system-ui">
    <h2>❌ Payment canceled</h2>
    <p>No charge was made.</p>
    <p><a href="/app/">Back to Dashboard</a></p>
    </body></html>
    """
