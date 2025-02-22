import os
import re
import subprocess
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import sys
from typing import List, Dict, Optional
import time
import random

def get_remote_branches() -> List[Dict[str, any]]:
    """Get list of remote branches with ranges"""
    try:
        result = subprocess.run(['git', 'branch', '-r'], capture_output=True, text=True)
        branches = result.stdout.strip().split('\n')
        
        # Extract range information from branch names
        range_patterns = []
        for branch in branches:
            branch = branch.strip()
            if 'origin/' in branch and '_to_' in branch:
                # Extract range numbers from branch name
                match = re.search(r'(\d+)_to_(\d+)$', branch)
                if match:
                    start, end = map(int, match.groups())
                    range_patterns.append({
                        'start': start,
                        'end': end,
                        'branch': branch.replace('origin/', '')
                    })
        
        return range_patterns
    except subprocess.SubprocessError as e:
        print(f"Error getting remote branches: {e}")
        return []

def get_image_url(repo_owner: str, repo_name: str, branch: str, folder: str, image_name: str) -> str:
    """Generate GitHub raw content URL for an image"""
    return f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/refs/heads/{branch}/{folder}/{image_name}"

def check_image_exists(url: str) -> bool:
    """Check if image exists at URL"""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_branch_contents(repo_owner: str, repo_name: str, branch: str, error_log_file: str) -> List[str]:
    """Get list of files and folders in a branch using GitHub API with retry logic"""
    max_retries = 3
    retry_delay = random.randint(300, 600)  # Random delay between 5-10 minutes
    
    for attempt in range(max_retries):
        try:
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/git/trees/{branch}?recursive=1"
            response = requests.get(api_url)
            response.raise_for_status()
            
            tree = response.json().get('tree', [])
            return [item['path'] for item in tree if item['type'] == 'blob' and item['path'].endswith('.jpg')]
            
        except requests.RequestException as e:
            error_msg = f"Error fetching branch {branch}: {str(e)}"
            print(error_msg)
            
            # Log the error
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(error_log_file, 'a') as f:
                f.write(f"{timestamp} - {error_msg}\n")
            
            # If rate limited, wait and retry
            if response.status_code == 403 and 'rate limit exceeded' in str(e):
                if attempt < max_retries - 1:
                    print(f"Rate limit exceeded. Waiting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                    # Generate new random delay for next attempt
                    retry_delay = random.randint(300, 600)
                    continue
            
            return []
    
    return []

def process_branch_images(branch_info: Dict[str, any], repo_owner: str, repo_name: str, failed_branches_file: str) -> List[str]:
    """Process images for a specific branch range"""
    valid_images = []
    branch = branch_info['branch']
    
    # Get all jpg files in the branch
    image_paths = get_branch_contents(repo_owner, repo_name, branch, failed_branches_file)
    
    if not image_paths:
        # Log failed branch
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(failed_branches_file, 'a') as f:
            f.write(f"{timestamp} - Failed to fetch contents for branch: {branch} (range: {branch_info['start']}-{branch_info['end']})\n")
        return []
    
    # Process each image file
    for image_path in image_paths:
        folder = os.path.dirname(image_path)
        image_name = os.path.basename(image_path)
        
        # Verify image is within the branch's range
        match = re.search(r'[a-z](\d+)\.jpg$', image_name.lower())
        if match:
            image_number = int(match.group(1))
            if branch_info['start'] <= image_number <= branch_info['end']:
                url = get_image_url(repo_owner, repo_name, branch, folder, image_name)
                if check_image_exists(url):
                    valid_images.append(url)
                    print(f"Found valid image: {url}")
    
    return valid_images

def extract_number_from_url(url: str) -> int:
    """Extract the image number from the URL for sorting"""
    match = re.search(r'[a-z](\d+)\.jpg$', url.lower())
    if match:
        return int(match.group(1))
    return 0

def main(repo_owner: str, repo_name: str, output_file: str):
    """Main function to process all branches and save results"""
    # Create logs directory if it doesn't exist
    logs_dir = 'logs'
    os.makedirs(logs_dir, exist_ok=True)
    
    # Initialize log files
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    failed_branches_file = os.path.join(logs_dir, f'failed_branches_{timestamp}.log')
    error_log_file = os.path.join(logs_dir, f'error_log_{timestamp}.log')
    
    print("Fetching remote branches...")
    branches = get_remote_branches()
    
    if not branches:
        print("No valid branches found")
        return False
    
    print(f"Found {len(branches)} valid branches")
    
    # First pass: Process all branches
    with ThreadPoolExecutor(max_workers=3) as executor:
        process_branch = partial(
            process_branch_images, 
            repo_owner=repo_owner, 
            repo_name=repo_name,
            failed_branches_file=failed_branches_file
        )
        results = list(executor.map(process_branch, branches))
    
    # Get failed branches from log file
    failed_branches = []
    if os.path.exists(failed_branches_file):
        with open(failed_branches_file, 'r') as f:
            for line in f:
                if 'Failed to fetch contents for branch:' in line:
                    match = re.search(r'branch: (\d+_to_\d+) \(range: (\d+)-(\d+)\)', line)
                    if match:
                        failed_branches.append({
                            'branch': match.group(1),
                            'start': int(match.group(2)),
                            'end': int(match.group(3))
                        })
    
    # Second pass: Retry failed branches
    if failed_branches:
        print(f"\nRetrying {len(failed_branches)} failed branches...")
        time.sleep(random.randint(300, 600))  # Wait 5-10 minutes before retrying
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            retry_results = list(executor.map(process_branch, failed_branches))
            
            # Add successful retries to results
            results.extend(retry_results)
    
    # Flatten results and sort images
    all_images = [url for branch_results in results for url in branch_results]
    
    if all_images:
        # Sort images
        all_images.sort(key=lambda x: (
            os.path.basename(x).lower(),
            extract_number_from_url(x)
        ))
        
        # Write results to file
        with open(output_file, 'w') as f:
            for url in all_images:
                f.write(f"{url}\n")
        
        # Create new success log
        success_log = os.path.join(logs_dir, f'success_images_{timestamp}.log')
        with open(success_log, 'w') as f:
            f.write(f"Successfully fetched and sorted images at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:\n")
            f.write(f"Total images found: {len(all_images)}\n\n")
            for url in all_images:
                f.write(f"{url}\n")
        
        print(f"\nFinal Summary:")
        print(f"Total branches processed: {len(branches)}")
        print(f"Initially failed branches: {len(failed_branches)}")
        print(f"Total images found: {len(all_images)}")
        
        return True
    else:
        print("No valid images found")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python fetch_branch_images.py <repo_owner> <repo_name> <output_file>")
        sys.exit(1)
    
    repo_owner = sys.argv[1]
    repo_name = sys.argv[2]
    output_file = sys.argv[3]
    
    success = main(repo_owner, repo_name, output_file)
    if not success:
        sys.exit(1) 