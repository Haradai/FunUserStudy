from PIL import Image
import os

def normalize_icons(input_dir, output_dir, target_size=(256, 256)):
    """
    Normalize all images in input_dir to target_size and save to output_dir.
    Uses center crop and resize to maintain aspect ratio while filling the target size.
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each image in the input directory
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            
            try:
                # Open the image
                with Image.open(input_path) as img:
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Calculate dimensions for center crop
                    width, height = img.size
                    target_ratio = target_size[0] / target_size[1]
                    current_ratio = width / height
                    
                    if current_ratio > target_ratio:
                        # Image is wider than target ratio
                        new_width = int(height * target_ratio)
                        left = (width - new_width) // 2
                        img = img.crop((left, 0, left + new_width, height))
                    else:
                        # Image is taller than target ratio
                        new_height = int(width / target_ratio)
                        top = (height - new_height) // 2
                        img = img.crop((0, top, width, top + new_height))
                    
                    # Resize to target size
                    img = img.resize(target_size, Image.Resampling.LANCZOS)
                    
                    # Save the normalized image
                    img.save(output_path, quality=95, optimize=True)
                    print(f"Processed {filename} -> {output_path}")
                    
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")

if __name__ == "__main__":
    input_dir = "icon_memes"
    output_dir = "icon_memes_normalized"
    normalize_icons(input_dir, output_dir) 