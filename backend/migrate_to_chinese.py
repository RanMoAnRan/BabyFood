import json
import os
import time
import sys

# 将 backend 目录加入 path 以便导入 utils
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from utils.translator import translate_text

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RECIPES_DIR = os.path.join(DATA_DIR, "recipes")

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def translate_recipe(data):
    # 标题 (Title)
    if "title" in data and data["title"]:
        print(f"  Translating title: {data['title']}")
        data["title"] = translate_text(data["title"])

    # 描述/贴士 (Nutrition Tip)
    if "nutrition_tip" in data and data["nutrition_tip"]:
        # print(f"  Translating tip...")
        data["nutrition_tip"] = translate_text(data["nutrition_tip"])

    # 食材 (Ingredients)
    if "ingredients" in data and isinstance(data["ingredients"], list):
        # print(f"  Translating ingredients...")
        for ing in data["ingredients"]:
            if "name" in ing:
                ing["name"] = translate_text(ing["name"])
            if "amount" in ing:
                # amount 通常包含单位，也可以翻译，比如 "1 cup" -> "1 杯"
                ing["amount"] = translate_text(ing["amount"])

    # 步骤 (Steps)
    if "steps" in data and isinstance(data["steps"], list):
        # print(f"  Translating steps...")
        for step in data["steps"]:
            if "text" in step:
                step["text"] = translate_text(step["text"])

    # 警告 (Warnings)
    if "warnings" in data and isinstance(data["warnings"], list):
        new_warnings = []
        for w in data["warnings"]:
            new_warnings.append(translate_text(w))
        data["warnings"] = new_warnings

    return data

def main():
    if not os.path.exists(RECIPES_DIR):
        print(f"Directory not found: {RECIPES_DIR}")
        return

    files = [f for f in os.listdir(RECIPES_DIR) if f.endswith(".json")]
    total = len(files)
    print(f"Found {total} recipes to process.")

    for i, filename in enumerate(files):
        path = os.path.join(RECIPES_DIR, filename)
        print(f"[{i+1}/{total}] Processing {filename}...")
        
        try:
            data = read_json(path)
            
            # 简单的判断：如果标题已经是中文（包含非 ASCII 字符），可能跳过？
            # 但考虑到可能是部分翻译，或者之前手动改的，我们这里假设只要是英文就翻译
            # 这里简单判断：如果 title 包含中文字符，则认为已翻译 (粗略)
            has_chinese = False
            for char in data.get("title", ""):
                if "\u4e00" <= char <= "\u9fff":
                    has_chinese = True
                    break
            
            if has_chinese and filename != "demo_pumpkin_potato.json": 
                # demo 本来就是中文
                print("  Skipping (already Chinese).")
                continue

            translated_data = translate_recipe(data)
            write_json(path, translated_data)
            
            # 避免 API 速率限制
            time.sleep(0.5)

        except Exception as e:
            print(f"  Error processing {filename}: {e}")

    print("Done!")

if __name__ == "__main__":
    main()
