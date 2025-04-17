import os
import pandas as pd
from tqdm import tqdm
from maktab_dl.handler import MaktabkhoonehCrawler
from maktab_dl.utils import get_cookies_default_file_path, sanitize_filename
import logging
from datetime import datetime
import time


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
        f.write("# Course: " + course_info.course.title + "\n")
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


def create_download_log(course_info, output_path):
    """Create an Excel log file to track download progress"""
    course_name = sanitize_filename(course_info.course.title)
    course_directory = os.path.join(output_path, course_name)
    os.makedirs(course_directory, exist_ok=True)
    # Initialize log data
    log_data = []
    for i, chapter in enumerate(course_info.chapters.chapters):
        chapter_title = f"{i + 1}_{sanitize_filename(chapter.title)}"
        chapter_directory = os.path.join(course_directory, chapter_title)
        for j, unit in enumerate(chapter.unit_set):
            unit_name = f"{j + 1}_{sanitize_filename(unit.title)}"
            # Check if this is a lecture with subtitle
            chapter_url = f"{chapter.slug}-ch{chapter.id}"
            unit_url = f"{course_info.link}{chapter_url}/{unit.slug}/"
            try:
                response = crawler.request(url=unit_url)
                response.raise_for_status()
                has_subtitle = bool(crawler._extract_subtitle_link(response.text))
            except:
                has_subtitle = False
            if has_subtitle:
                # For lectures with subtitles, files are stored in a subfolder
                base_name = os.path.splitext(unit_name)[0]
                file_path = os.path.join(chapter_directory, base_name, base_name)
            else:
                # For other units, files are stored directly in chapter directory
                file_path = os.path.join(chapter_directory, unit_name)
            # Check if files exist and set initial status
            status = 'Pending'
            if has_subtitle:
                # Check for video and subtitle files
                video_ext = 'mp4'  # Default video extension
                video_path = f"{file_path}.{video_ext}"
                subtitle_path = f"{file_path}.vtt"
                if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                    status = 'Already Exists'
                elif os.path.exists(subtitle_path) and os.path.getsize(subtitle_path) > 0:
                    status = 'Already Exists'
            else:
                # Check for regular files
                possible_extensions = ['.mp4', '.vtt', '.pdf', '.zip', '.rar','.html']
                for ext in possible_extensions:
                    full_path = f"{file_path}{ext}"
                    if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                        status = 'Already Exists'
                        break
            log_data.append({
                'Chapter': chapter.title,
                'Chapter Directory': chapter_title,
                'Unit': unit.title,
                'Unit Name': unit_name,
                'Type': unit.type,
                'File Path': file_path,
                'Status': status,
                'Download Time': '',
                'File Size': '',
                'Error': ''
            })
    # Create DataFrame and save to Excel
    df = pd.DataFrame(log_data)
    log_path = os.path.join(course_directory, f'{course_name}_download_log.xlsx')
    df.to_excel(log_path, index=False)
    return log_path


def update_download_log(log_path, chapter_title, unit_name, status, file_size='', error=''):
    """Update the download log Excel file with new information"""
    try:
        df = pd.read_excel(log_path)
        mask = (df['Chapter'] == chapter_title) & (df['Unit Name'] == unit_name)
        if mask.any():
            df.loc[mask, 'Status'] = status
            df.loc[mask, 'Download Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if file_size:
                df.loc[mask, 'File Size'] = file_size
            if error:
                df.loc[mask, 'Error'] = error
            df.to_excel(log_path, index=False)
    except Exception as e:
        logging.error(f"Error updating download log: {e}")


def download_course_content(crawler, course_info):
    """Download all course content"""
    print("\nStarting video downloads...")
    # Create download log
    log_path = create_download_log(course_info, crawler.output_path)
    print(f"Download log created at: {log_path}")
    try:
        # Use the original download functionality
        crawler.download_course_videos(course_info)
        # After download completes, update the log with final status
        for chapter in course_info.chapters.chapters:
            for unit in chapter.unit_set:
                # Check if files were downloaded
                chapter_url = f"{chapter.slug}-ch{chapter.id}"
                unit_url = f"{course_info.link}{chapter_url}/{unit.slug}/"
                try:
                    response = crawler.request(url=unit_url)
                    response.raise_for_status()
                    # Check for downloaded files
                    video_urls = crawler._extract_video_link(response.text)
                    subtitle_url = crawler._extract_subtitle_link(response.text)
                    attachment_url = crawler._extract_attachment_link(response.text)
                    # Get the expected file paths
                    chapter_title = f"{chapter.title}"
                    unit_name = f"{unit.title}"
                    # Determine status based on downloaded files
                    if video_urls:
                        # Check if video file exists
                        video_ext = video_urls[0].split("?")[0].split(".")[-1]
                        if subtitle_url:
                            # For lectures with subtitles, check in subfolder
                            base_name = os.path.splitext(unit_name)[0]
                            video_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                    f"{chapter_title}", base_name, f"{base_name}.{video_ext}")
                        else:
                            video_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                    f"{chapter_title}", f"{unit_name}.{video_ext}")
                        if os.path.exists(video_path):
                            status = 'Already Exists' if os.path.getsize(video_path) > 0 else 'Downloaded'
                        else:
                            status = 'Failed'
                    elif subtitle_url:
                        # Check if subtitle file exists
                        subtitle_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                  f"{chapter_title}", f"{unit_name}.vtt")
                        if os.path.exists(subtitle_path):
                            status = 'Already Exists' if os.path.getsize(subtitle_path) > 0 else 'Downloaded'
                        else:
                            status = 'Failed'
                    elif attachment_url:
                        # Check if attachment exists
                        attachment_name = attachment_url.split("?")[0].split("/")[-1]
                        attachment_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                    f"{chapter_title}", f"{unit_name}_{sanitize_filename(attachment_name)}")
                        if os.path.exists(attachment_path):
                            status = 'Already Exists' if os.path.getsize(attachment_path) > 0 else 'Downloaded'
                        else:
                            status = 'Failed'
                    else:
                        status = 'No Content'
                    update_download_log(log_path, chapter_title, unit_name, status)
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"Error checking download status for unit {unit.title}: {error_msg}")
                    update_download_log(log_path, chapter_title, unit_name, 'Failed', error=error_msg)
                    continue
    except Exception as e:
        logging.error(f"Error in download process: {e}")
        raise
    print("\nDownload completed successfully!")
    print(f"Download log updated at: {log_path}")


def download_from_courses_file(crawler):
    """Download courses from courses.txt file"""
    print("\nStarting batch download from courses.txt...")
    # Read course URLs from file
    courses_file = "courses.txt"
    if not os.path.exists(courses_file):
        print(f"Error: {courses_file} not found")
        return
    with open(courses_file, 'r', encoding='utf-8') as f:
        course_urls = [line.strip() for line in f if line.strip()]
    if not course_urls:
        print("Error: No course URLs found in courses.txt")
        return
    print(f"Found {len(course_urls)} courses to download")
    for i, course_url in enumerate(course_urls, 1):
        try:
            print(f"\nProcessing course {i}/{len(course_urls)}: {course_url}")
            # Crawl course info
            print("Fetching course information...")
            course_info = crawler.crawl_course_link(course_url)
            # Create download log for this course
            log_path = create_download_log(course_info, crawler.output_path)
            print(f"Download log created at: {log_path}")
            # Enroll in the course
            print("Enrolling in course...")
            crawler.enroll_course_link(course_url)
            # Download course videos
            print("Starting downloads...")
            crawler.download_course_videos(course_info)
            # After download completes, update the log with final status
            print("Updating download log...")
            for chapter in course_info.chapters.chapters:
                for unit in chapter.unit_set:
                    # Check if files were downloaded
                    chapter_url = f"{chapter.slug}-ch{chapter.id}"
                    unit_url = f"{course_info.link}{chapter_url}/{unit.slug}/"
                    try:
                        response = crawler.request(url=unit_url)
                        response.raise_for_status()
                        # Check for downloaded files
                        video_urls = crawler._extract_video_link(response.text)
                        subtitle_url = crawler._extract_subtitle_link(response.text)
                        attachment_url = crawler._extract_attachment_link(response.text)
                        # Get the expected file paths
                        chapter_title = f"{chapter.title}"
                        unit_name = f"{unit.title}"
                        # Determine status based on downloaded files
                        if video_urls:
                            # Check if video file exists
                            video_ext = video_urls[0].split("?")[0].split(".")[-1]
                            if subtitle_url:
                                # For lectures with subtitles, check in subfolder
                                base_name = os.path.splitext(unit_name)[0]
                                video_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                        f"{chapter_title}", base_name, f"{base_name}.{video_ext}")
                            else:
                                video_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                        f"{chapter_title}", f"{unit_name}.{video_ext}")
                            if os.path.exists(video_path):
                                status = 'Already Exists' if os.path.getsize(video_path) > 0 else 'Downloaded'
                            else:
                                status = 'Failed'
                        elif subtitle_url:
                            # Check if subtitle file exists
                            subtitle_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                      f"{chapter_title}", f"{unit_name}.vtt")
                            if os.path.exists(subtitle_path):
                                status = 'Already Exists' if os.path.getsize(subtitle_path) > 0 else 'Downloaded'
                            else:
                                status = 'Failed'
                        elif attachment_url:
                            # Check if attachment exists
                            attachment_name = attachment_url.split("?")[0].split("/")[-1]
                            attachment_path = os.path.join(crawler.output_path, sanitize_filename(course_info.course.title),
                                                        f"{chapter_title}", f"{unit_name}_{sanitize_filename(attachment_name)}")
                            if os.path.exists(attachment_path):
                                status = 'Already Exists' if os.path.getsize(attachment_path) > 0 else 'Downloaded'
                            else:
                                status = 'Failed'
                        else:
                            status = 'No Content'
                        update_download_log(log_path, chapter_title, unit_name, status)
                    except Exception as e:
                        error_msg = str(e)
                        logging.error(f"Error checking download status for unit {unit.title}: {error_msg}")
                        update_download_log(log_path, chapter_title, unit_name, 'Failed', error=error_msg)
                        continue
            print(f"Successfully processed course: {course_info.course.title}")
            print(f"Download log updated at: {log_path}")
            # Add a small delay between courses
            time.sleep(2)
        except Exception as e:
            print(f"Error processing course {course_url}: {e}")
            logging.error(f"Error processing course {course_url}: {e}")
            continue
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