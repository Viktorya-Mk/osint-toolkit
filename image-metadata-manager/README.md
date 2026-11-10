# Image Metadata Manager

A small command line tool to inspect, export and strip EXIF metadata from images.

## Features
- Lists every image in `media/` and lets you pick one by number
- Terminal view of file info, EXIF tags and GPS data
- Converts GPS coordinates to decimal degrees and builds a map link
- Exports metadata as structured JSON to `output/`
- Saves a metadata free copy to `output/cleaned/` (the original is never modified)

Example:
<img width="462" height="246" alt="example" src="https://github.com/user-attachments/assets/35bd570a-35cf-4152-8ac9-d5d85964bb3e" />


## Usage
```
pip install -r requirements.txt
python main.py
```
Drop your images in the `media/` folder first. Supported: JPG, PNG, TIFF, WebP.

## Privacy note
Photos taken with phones often embed the exact location where they were taken.
Use the clean copy option before sharing images publicly.
