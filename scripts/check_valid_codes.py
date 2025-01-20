import os
import sys
import requests
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import time
from datetime import datetime

def check_code(code, prefix):
    """Check if an image code is valid"""
    code_str = f"{prefix}{code}"
    url = f"https://fgo.vn/tai-anh-ve/?id={code_str}"
    
    try:
        # Add delay to prevent rate limiting
        time.sleep(0.1)
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Check if the response indicates an invalid code
        if "Mã hình ảnh không đúng!" in response.text:
            return None
            
        return code_str
        
    except requests.RequestException:
        return None
    except Exception:
        return None

def scan_range(prefix, start_code, end_code, output_file):
    """Scan a range of codes and log valid ones"""
    
    def process_batch(codes):
        checker = partial(check_code, prefix=prefix)
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(checker, codes)
            valid_codes = [code for code in results if code]
            return valid_codes
    
    # Process in smaller batches to manage memory
    batch_size = 100
    current_start = start_code
    
    while current_start <= end_code:
        current_end = min(current_start + batch_size, end_code + 1)
        batch_codes = range(current_start, current_end)
        
        valid_codes = process_batch(batch_codes)
        
        # Log valid codes
        if valid_codes:
            with open(output_file, 'a') as f:
                for code in valid_codes:
                    f.write(f"{code}\n")
        
        current_start = current_end

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python check_valid_codes.py <prefix> <start_code> <end_code> <output_file>")
        sys.exit(1)

    prefix = sys.argv[1]
    start_code = int(sys.argv[2])
    end_code = int(sys.argv[3])
    output_file = sys.argv[4]
    
    # Create or clear the output file
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    scan_range(prefix, start_code, end_code, output_file)

    # When writing to the log file, use append mode ('a') instead of write mode ('w')
    with open(output_file, 'a') as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Scan completed\n") 