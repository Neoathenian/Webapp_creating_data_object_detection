import json
import os
from pathlib import Path

webapp_storage = Path("local_storage")
api_results_dir = Path("../API_Object_detection/src_temp_algorithms/results/prediction_cache/text_information_v7")

def port_evaluations():
    if not api_results_dir.exists():
        print(f"Results dir {api_results_dir} not found")
        return
    
    count = 0
    for user_dir in webapp_storage.iterdir():
        if not user_dir.is_dir(): continue
        data_collector_dir = user_dir / "data_collector"
        if not data_collector_dir.exists(): continue
        
        for template_dir in data_collector_dir.iterdir():
            if not template_dir.is_dir(): continue
            for item_dir in template_dir.iterdir():
                if not item_dir.is_dir(): continue
                doc_path = item_dir / "doc.json"
                if not doc_path.exists(): continue
                
                try:
                    with open(doc_path, "r", encoding="utf-8") as f:
                        doc = json.load(f)
                except Exception as e:
                    print(f"Error reading {doc_path}: {e}")
                    continue
                
                sha = item_dir.name
                
                found_json = None
                for p in api_results_dir.rglob(f"{sha}.json"):
                    found_json = p
                    break
                    
                if not found_json:
                    continue
                    
                count += 1
                with open(found_json, "r", encoding="utf-8") as f:
                    pred_data = json.load(f)
                
                prediction = pred_data.get("prediction", {})
                metrics = pred_data.get("metrics", {})
                
                doc["predicted_extract_text"] = []
                doc["predicted_references"] = []
                doc["predicted_noise"] = []
                
                for rect in prediction.get("rectangles", []):
                    bbox = rect.get("bbox_xywh")
                    if bbox:
                        r = {
                            "id": rect.get("id"),
                            "name": rect.get("name"),
                            "x": bbox[0],
                            "y": bbox[1],
                            "w": bbox[2],
                            "h": bbox[3],
                            "extract_text": True
                        }
                        doc["predicted_extract_text"].append(r)
                
                for cr in prediction.get("curved_regions", []):
                    bbox = cr.get("bbox_xywh")
                    if bbox:
                        r = {
                            "id": cr.get("id"),
                            "name": cr.get("name"),
                            "x": bbox[0],
                            "y": bbox[1],
                            "w": bbox[2],
                            "h": bbox[3],
                            "extract_text": True
                        }
                        doc["predicted_extract_text"].append(r)
                        
                doc["evaluation"] = {
                    "success": metrics.get("detection_success", False),
                    "confidence_score": metrics.get("confidence_score", 0.0),
                    "mean_iou": metrics.get("mean_iou", 0.0),
                    "median_iou": metrics.get("median_iou", 0.0),
                    "recall_iou_50": metrics.get("recall_iou_50", 0.0)
                }
                
                # Also store individual box ious!
                for rm in metrics.get("rectangles", []):
                    r_id = rm.get("id")
                
                # The prompt asks for: "Finally, I also want displayed the IoU score for each of the predictions"
                # So we can lookup the IoU for each prediction in `metrics.get("rectangles")`.
                # If we map the ID or name. Wait, let's just dump metrics["rectangles"] so the frontend can look it up.
                doc["evaluation"]["rectangles_metrics"] = metrics.get("rectangles", [])
                
                with open(doc_path, "w", encoding="utf-8") as f:
                    json.dump(doc, f, indent=2)
                
    print(f"Updated {count} documents.")

if __name__ == '__main__':
    port_evaluations()
