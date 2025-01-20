import os
import re
import shutil
from datetime import datetime
import subprocess

def get_remote_branches():
    """Get list of remote branches with ranges"""
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

def get_image_number(filename):
    """Extract number from image filename (e.g., s89120.jpg -> 89120)"""
    match = re.search(r'[a-z](\d+)\.jpg$', filename.lower())
    if match:
        return int(match.group(1))
    return None

def get_image_prefix(filename):
    """Extract prefix from image filename (e.g., s89120.jpg -> s)"""
    match = re.search(r'^([a-z])\d+\.jpg$', filename.lower())
    if match:
        return match.group(1)
    return None

def organize_images():
    # Get all range patterns from remote branches
    range_patterns = get_remote_branches()
    
    # Get current date in YYYYMMDD format
    today = datetime.now().strftime('%Y%m%d')
    
    # Find all image folders in root directory
    image_folders = [f for f in os.listdir('.') if f.startswith('images_') and os.path.isdir(f)]
    
    # Track statistics
    stats = {'processed': 0, 'moved': 0, 'errors': 0}
    
    for folder in image_folders:
        print(f"\nProcessing folder: {folder}")
        
        # Process each image in the folder
        for filename in os.listdir(folder):
            if not filename.lower().endswith('.jpg'):
                continue
                
            stats['processed'] += 1
            
            # Extract number and prefix from filename
            number = get_image_number(filename)
            prefix = get_image_prefix(filename)
            
            if not number or not prefix:
                print(f"Skipping invalid filename: {filename}")
                stats['errors'] += 1
                continue
            
            # Find matching range
            matching_range = None
            for range_pattern in range_patterns:
                if range_pattern['start'] <= number <= range_pattern['end']:
                    matching_range = range_pattern
                    break
            
            if matching_range:
                # Create target folder name
                target_folder = f"images_{prefix}_{today}_{matching_range['start']}_to_{matching_range['end']}"
                
                # Create target folder if it doesn't exist
                os.makedirs(target_folder, exist_ok=True)
                
                # Move file to target folder
                source_path = os.path.join(folder, filename)
                target_path = os.path.join(target_folder, filename)
                
                try:
                    shutil.move(source_path, target_path)
                    stats['moved'] += 1
                    print(f"Moved {filename} to {target_folder}")
                except Exception as e:
                    print(f"Error moving {filename}: {e}")
                    stats['errors'] += 1
            else:
                print(f"No matching range found for {filename}")
                stats['errors'] += 1
    
    # Print summary
    print("\nOrganization complete!")
    print(f"Total files processed: {stats['processed']}")
    print(f"Files moved: {stats['moved']}")
    print(f"Errors: {stats['errors']}")

if __name__ == "__main__":
    organize_images() 