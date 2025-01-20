import os
import requests
import datetime
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from io import BytesIO
from PIL import Image

def is_valid_image(content):
    try:
        img = Image.open(BytesIO(content))
        img.verify()
        return True
    except Exception:
        return False

def download_image(code, prefix, base_folder):
    code_str = f"{prefix}{code}"
    url = f"https://fgo.vn/tai-anh-ve/?id={code_str}"
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        content = response.content

        if not is_valid_image(content):
            print(f"Invalid image content for {url}")
            return False

        if "Mã hình ảnh không đúng!" in response.text:
            print(f"Invalid image code for {url}")
            return False

        image_path = os.path.join(base_folder, f"{code_str}.jpg")
        
        with open(image_path, "wb") as file:
            file.write(content)

        print(f"Downloaded and saved: {image_path}")
        return True

    except requests.RequestException as e:
        print(f"Failed to download {url}: {e}")
        return False
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python script.py <prefix> <start_code> <end_code> <output_folder>")
        sys.exit(1)

    prefix = sys.argv[1]
    start_code = int(sys.argv[2])
    end_code = int(sys.argv[3])
    output_dir = sys.argv[4]

    os.makedirs(output_dir, exist_ok=True)

    with ThreadPoolExecutor(max_workers=5) as executor:
        codes = range(start_code, end_code + 1)
        download_with_params = partial(download_image, prefix=prefix, base_folder=output_dir)
        results = list(executor.map(download_with_params, codes))

    successful = sum(1 for r in results if r)
    print(f"Downloaded {successful} images out of {len(results)} attempts")
