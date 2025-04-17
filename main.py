import os
import pandas as pd
from tqdm import tqdm
from maktab_dl.handler import MaktabkhoonehCrawler
from maktab_dl.utils import get_cookies_default_file_path, sanitize_filename
import logging

def export_to_excel(course_info, output_path):
    """Export course information to Excel file"""
    # Create course directory
    course_name = sanitize_filename(course_info.course.title)
    course_dir = os.path.join(output_path, course_name)
    os.makedirs(course_dir, exist_ok=True)
    
    data = []
    for chapter in course_info.chapters.chapters:
        for unit in chapter.unit_set:
            data.append({
                'Chapter': chapter.title,
                'Unit': unit.title,
                'Type': unit.type,
                'Description': unit.description,
                'Has Attachment': 'Yes' if unit.attachment else 'No',
                'Project Required': 'Yes' if unit.project_required else 'No',
                'Status': 'Active' if unit.status else 'Inactive'
            })
    
    df = pd.DataFrame(data)
    excel_path = os.path.join(course_dir, f'{course_name}.xlsx')
    df.to_excel(excel_path, index=False)
    print(f"Course information exported to: {excel_path}")

def save_links_to_file(course_info, output_path, crawler):
    """Save all download links to a text file in IDM-friendly format"""
    # Create course directory
    course_name = sanitize_filename(course_info.course.title)
    course_dir = os.path.join(output_path, course_name)
    os.makedirs(course_dir, exist_ok=True)
    
    links_file = os.path.join(course_dir, f'{course_name}_links.txt')
    with open(links_file, 'w', encoding='utf-8') as f:
        f.write("# Course: " + course_info.course.title + "\n\n")
        
        for chapter in course_info.chapters.chapters:
            f.write(f"# Chapter: {chapter.title}\n")
            
            for unit in chapter.unit_set:
                # Get the unit URL
                chapter_url = f"{chapter.slug}-ch{chapter.id}"
                unit_url = f"{course_info.link}{chapter_url}/{unit.slug}/"
                
                try:
                    # Get the page content
                    response = crawler.request(url=unit_url)
                    response.raise_for_status()
                    
                    # Extract video URLs
                    video_urls = crawler._extract_video_link(response.text)
                    for url in video_urls:
                        if not url.startswith('http'):
                            url = f"{crawler.BASE_URL}{url}"
                        f.write(f"{url}\n")
                    
                    # Extract subtitle URLs
                    subtitle_url = crawler._extract_subtitle_link(response.text)
                    if subtitle_url:
                        if not subtitle_url.startswith('http'):
                            subtitle_url = f"{crawler.BASE_URL}{subtitle_url}"
                        f.write(f"{subtitle_url}\n")
                    
                    # Extract attachment URLs
                    attachment_url = crawler._extract_attachment_link(response.text)
                    if attachment_url:
                        if not attachment_url.startswith('http'):
                            attachment_url = f"{crawler.BASE_URL}{attachment_url}"
                        f.write(f"{attachment_url}\n")
                    
                    # Extract RAR/ZIP files
                    file_urls = crawler._extract_files_from_html(response.text)
                    for url in file_urls:
                        f.write(f"{url}\n")
                        
                except Exception as e:
                    logging.error(f"Error getting URLs for unit {unit.title}: {e}")
                    continue
    
    print(f"Download links saved to: {links_file}")

def download_course_content(crawler, course_info):
    """Download all course content"""
    print("\nStarting video downloads...")
    crawler.download_course_videos(course_info)
    print("\nDownload completed successfully!")

def download_from_courses_file(crawler):
    """Download courses from courses.txt file"""
    print("\nStarting batch download from courses.txt...")
    crawler.download_courses_from_file()
    print("\nBatch download completed!")

def main():
    print("Maktab Downloader")
    print("=" * 50)
    
    # Get output directory
    output_dir = input("\nEnter output directory (press Enter for current directory): ").strip()
    if not output_dir:
        output_dir = os.getcwd()
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get download options
    print("\nSelect download option:")
    print("1. Download single course content")
    print("2. Extract data to Excel")
    print("3. Save download URLs only")
    print("4. Download from courses.txt")
    
    option = input("\nEnter option number (1-4): ").strip()
    
    try:
        # Initialize crawler
        cookies_path = get_cookies_default_file_path()
        
        if not os.path.exists(cookies_path):
            print("\nFirst time setup - Please enter your Maktabkhooneh credentials")
            username = input("Enter Username: ")
            password = input("Enter Password: ")
            crawler = MaktabkhoonehCrawler(
                username=username,
                password=password,
                cookies_path=cookies_path,
                output_path=output_dir
            )
            crawler.login(force_save_cookies=True)
        else:
            crawler = MaktabkhoonehCrawler(
                cookies_path=cookies_path,
                output_path=output_dir
            )
            crawler.init_cookies()
        
        if option == "4":
            # Download from courses.txt
            download_from_courses_file(crawler)
        else:
            # Get course URL for other options
            course_url = input("\nEnter course URL: ").strip()
            if not course_url:
                print("Error: Course URL is required")
                return
            
            # Get course info
            print("\nFetching course information...")
            course_info = crawler.crawl_course_link(input_link=course_url)
            
            if option == "1":
                # Download all content
                download_course_content(crawler, course_info)
            elif option == "2":
                # Extract data to Excel
                export_to_excel(course_info, output_dir)
            elif option == "3":
                # Save download URLs only
                save_links_to_file(course_info, output_dir, crawler)
            else:
                print("Error: Invalid option selected")
                return
            
        print("\nOperation completed successfully!")
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        logging.error(f"Error in main: {e}", exc_info=True)

if __name__ == "__main__":
    main() 