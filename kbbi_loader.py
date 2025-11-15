import os
import json

def load_kbbi(folder_path="sambungkata"):
    kbbi_words = set()

    for fname in os.listdir(folder_path):
        if fname.startswith("kbbi_v_part") and fname.endswith(".json"):
            path = os.path.join(folder_path, fname)
            print(f"[KBBI] Loading: {path}")

            try:
                with open(path, "r", encoding="utf8") as f:
                    data = json.load(f)

                    # JSON kamu formatnya dictionary: { "anjing": {...} }
                    for word in data.keys():
                        kbbi_words.add(word.lower().strip())

            except Exception as e:
                print(f"[KBBI] ERROR loading {fname}: {e}")

    print(f"[KBBI] TOTAL KATA TERLOAD: {len(kbbi_words)}")
    return kbbi_words
