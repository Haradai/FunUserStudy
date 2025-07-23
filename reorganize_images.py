import os
import shutil
from pathlib import Path

def get_image_id(filename):
    # Extract the ID from the filename (everything after the last underscore)
    return filename.split('_')[-1].split(".")[0]

def main():
    # Define paths
    sr_dir = Path('static/SR')
    hq_dir = Path('static/GT')
    
    # Create a mapping of HQ images by their ID
    hq_images = {}
    for hq_file in hq_dir.glob('*'):
        if hq_file.is_file():
            hq_id = get_image_id(hq_file.name)
            hq_images[hq_id] = hq_file
    
    # Process each SR image
    for sr_file in sr_dir.glob('*'):
        if sr_file.is_file():
            sr_id = get_image_id(sr_file.name)
            
            # Find corresponding HQ image
            if sr_id in hq_images:
                hq_file = hq_images[sr_id]
                
                # Create new filename using SR image's name
                new_hq_name = sr_file.name
                new_hq_path = hq_dir / new_hq_name
                
                # Copy the HQ image with the new name
                shutil.copy2(hq_file, new_hq_path)
                print(f"Created {new_hq_name} from {hq_file.name}")
            else:
                print(f"Warning: No matching HQ image found for {sr_file.name}")

if __name__ == "__main__":
    main() 