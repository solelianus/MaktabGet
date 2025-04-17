import httpx
from maktab_dl.utils import (
    save_cookies,
    load_cookies,
    sanitize_filename,
    get_cookies_default_file_path,
)
import logging
from maktab_dl.schemas import (
    LoginResponse,
    UserInfo,
    CourseModel,
    CourseChaptersModel,
    CourseInfo,
)
from tqdm import tqdm
import os
import lxml.html
import random
import time


class MaktabkhoonehCrawler:
    name: str = "Maktabkhooneh"
    BASE_URL: str = "https://maktabkhooneh.org"
    AUTH_API_URL: str = "https://maktabkhooneh.org/api/v1/auth"
    COURSE_API_URL: str = "https://maktabkhooneh.org/api/v1/courses"

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        client: httpx.Client | None = None,
        headers: dict | None = None,
        cookies_path: str | None = None,
        output_path: str | None = None,
        proxy: str | None = None,
        *args,
        **kwargs,
    ):
        self.username: str | None = username
        self.password: str | None = password
        self.user_info: UserInfo | None = None
        self._client: httpx.Client | None = client
        self.headers: dict | None = headers or {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://maktabkhooneh.org",
            "priority": "u=1, i",
            "referer": "https://maktabkhooneh.org/",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "x-csrftoken": "RlHpENEdQEjIZkKoqh9dUG9nqSDiomk8l1XsOBbkdCcaIS8rljG6n09n7MX1aYNe",
            "x-requested-with": "XMLHttpRequest",
        }

        self.cookies_path: str = cookies_path or get_cookies_default_file_path()

        self.output_path = output_path or os.path.expanduser("~")
        if os.path.exists(self.output_path) is False:
            os.makedirs(self.output_path)
        self.proxy = proxy
        super().__init__(*args, **kwargs)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(follow_redirects=True, proxy=self.proxy)
        return self._client

    @client.setter
    def client(self, value: httpx.Client):
        self._client = value

    def init_cookies(self):
        load_cookies(self.client, self.cookies_path)

    def request(
        self,
        method: str = "GET",
        url: str = "",
        headers: dict = {},
        params: dict | None = None,
        data: dict | None = None,
        files: list | None = None,
    ):
        for i in range(3):
            try:
                response = self.client.request(
                    method, url, headers=headers, params=params, data=data, files=files
                )
                response.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logging.error("Too many requests. Sleeping for 60 seconds")
                    time.sleep(60)
                    continue
                elif e.response.status_code == 403:
                    logging.error(f"Forbidden error in url {url}: {e}")
                    # {"detail":"CSRF Failed: CSRF token missing or incorrect."}
                    detail = response.json()["detail"]
                    if "CSRF Failed" in detail:
                        logging.error(detail)
                        self.headers["x-csrftoken"] = self.client.cookies["csrftoken"]
                    continue
                else:
                    raise e
            except Exception as e:
                print(f"Error in url {url}")
                print(e)
                continue
        response.raise_for_status()
        return response

    # other methods and attributes

    def login(self, force_save_cookies: bool = True) -> UserInfo | None:
        url = f"{self.AUTH_API_URL}/check-active-user"
        payload = {"tessera": self.username, "g-recaptcha-response": "recaptcha-token"}

        response = self.request("POST", url, headers=self.headers, data=payload)
        response.raise_for_status()

        res = LoginResponse(**response.json())
        match res.message:
            case "get-pass":
                logging.info("success verify user")
            case "get-token":
                logging.error("user not exist. You must sign up first.")
                raise Exception(res.message)
            case "invalid-format":
                logging.error("Username is in ivalid format")
                raise Exception(res.message)
            case _:
                raise Exception(response.message)

        url = f"{self.AUTH_API_URL}/login-authentication"
        csrfmiddlewaretoken = self.client.cookies.get("csrftoken", "")
        payload = {
            "csrfmiddlewaretoken": csrfmiddlewaretoken,
            "tessera": self.username,
            "hidden_username": self.username,
            "password": self.password,
            "g-recaptcha-response": "recaptcha-token",
        }
        response = self.request("POST", url, headers=self.headers, data=payload)
        # response = self.client.request("POST", url, headers=self.headers, data=payload)
        response.raise_for_status()
        res = LoginResponse(**response.json())

        match res.message:
            case "logined":
                self.user_info = UserInfo(**response.json())
            case _:
                logging.error(f"Error on login with password: {response.text}")
                raise Exception(res.message)
        if force_save_cookies:
            save_cookies(self.client, self.cookies_path)
        return self.user_info

    def _clean_course_link(self, link: str) -> str:
        logging.info(f"Cleaning course link: {link}")
        if not link.startswith("https://"):
            link = "https://" + link.replace("http://", "")
        cleaned = link.split("?")[0].split("#")[0]
        # add / to end if not have
        if cleaned[-1] != "/":
            cleaned += "/"
        logging.info(f"Cleaned course link: {cleaned}")
        return cleaned

    def _crawl_course(self, course_name: str) -> CourseModel:
        logging.info(f"Crawling course info: {course_name}")
        url = f"{self.COURSE_API_URL}/{course_name}"
        response = self.request(url=url)
        response.raise_for_status()
        output = CourseModel(**response.json())
        return output

    def _crawl_course_chapters(self, course_name: str) -> CourseChaptersModel:
        logging.info(f"Crawling course chapters: {course_name}")

        url = f"{self.COURSE_API_URL}/{course_name}chapters/"
        response = self.request(url=url)
        response.raise_for_status()
        output = CourseChaptersModel(**response.json())
        return output

    def crawl_course_link(self, input_link: str) -> CourseInfo:
        link = self._clean_course_link(input_link)
        logging.info(f"Course info crawl started for link: {link}")
        logging.info(f"Extract Course name from link: {link}")
        course_name = link.split("course/")[-1]
        course = self._crawl_course(course_name)
        chapters = self._crawl_course_chapters(course_name)
        output = CourseInfo(link=link, course=course, chapters=chapters)
        logging.info(f"Course info crawl finished for link: {link}")
        return output

    def enroll_course_link(self, link: str) -> CourseModel:
        logging.info(f"Enroll course started for link: {link}")
        logging.info(f"Extract Course name from link: {link}")
        course_name = link.split("course/")[-1]
        url = f"{self.COURSE_API_URL}/{course_name}enroll/"
        response = self.request(method="POST", headers=self.headers, url=url)
        response.raise_for_status()
        logging.info(f"Enroll course finished for link: {link}")
        return CourseModel(**response.json())

    def _download(self, url, output_file: str):
        logging.info(f"Downloading url: {url}")
        try:
            head_response = self.client.head(url)
            head_response.raise_for_status()
            file_size = int(
                head_response.headers.get("content-length", 0)
            )  # Total file size
            if os.path.exists(output_file):
                logging.info(f"File already exists: {output_file}")
                # check size
                if os.path.getsize(output_file) == file_size:
                    logging.info(f"File already downloaded: {output_file}")
                    return False
                else:
                    logging.info(
                        f"File already exists but size is different: {output_file}"
                    )
                    os.remove(output_file)
            with self.client.stream("GET", url) as response:
                response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
                # Open the output file in write-binary mode
                with tqdm(
                    total=file_size,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"📥 {os.path.basename(output_file)}",
                    bar_format='{desc:30} {percentage:3.0f}% |{bar:40}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
                    colour='green',
                    ncols=100,
                    ascii=False,
                    dynamic_ncols=True
                ) as progress_bar:
                    with open(output_file, "wb") as file:
                        # Iterate over the response content in chunks
                        for chunk in response.iter_bytes(chunk_size=8192):
                            file.write(chunk)
                            progress_bar.update(len(chunk))
            logging.info(f"File downloaded successfully to {output_file}")
            return True
        except httpx.RequestError as e:
            logging.error(f"An error occurred while requesting the file: {e}")
            return False
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return False

    def _download_video(
        self,
        video_url: str,
        output_file: str,
    ) -> bool:
        logging.info(f"Downloading video: {video_url}")
        try:
            head_response = self.client.head(video_url)
            head_response.raise_for_status()
            file_size = int(
                head_response.headers.get("content-length", 0)
            )  # Total file size
            if os.path.exists(output_file):
                logging.info(f"File already exists: {output_file}")
                # check size
                if os.path.getsize(output_file) == file_size:
                    logging.info(f"File already downloaded: {output_file}")
                    return False
                else:
                    logging.info(
                        f"File already exists but size is different: {output_file}"
                    )
                    os.remove(output_file)
            with self.client.stream("GET", video_url) as response:
                response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
                # Open the output file in write-binary mode
                with tqdm(
                    total=file_size,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"🎥 {os.path.basename(output_file)}",
                    bar_format='{desc:30} {percentage:3.0f}% |{bar:40}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
                    colour='green',
                    ncols=100,
                    ascii=False,
                    dynamic_ncols=True
                ) as progress_bar:
                    with open(output_file, "wb") as file:
                        # Iterate over the response content in chunks
                        for chunk in response.iter_bytes(chunk_size=8192):
                            if chunk:
                                file.write(chunk)
                                progress_bar.update(len(chunk))
            return True
        except Exception as e:
            logging.error(f"Error downloading video: {e}")
            return False

    def _download_subtitle(
        self,
        subtitle_url,
        output_file,
    ) -> bool:
        logging.info(f"Downloading subtitle: {subtitle_url}")
        try:
            # Download the subtitle file
            response = self.client.get(subtitle_url)
            response.raise_for_status()
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Save the subtitle content
            with open(output_file, 'wb') as f:
                f.write(response.content)
            
            logging.info(f"Subtitle downloaded successfully to: {output_file}")
            return True
        except Exception as e:
            logging.error(f"Error downloading subtitle: {e}")
            return False

    def _extract_video_link(self, response_text: str) -> list[str]:
        html = lxml.html.fromstring(response_text)
        links = html.xpath("//source/attribute::src")
        return links

    def _extract_subtitle_link(self, response_text: str) -> str | None:
        html = lxml.html.fromstring(response_text)
        subtitles = html.xpath('//track[@kind="subtitles"]/@src')
        return next(iter(subtitles), None)

    def _extract_attachment_link(self, response_text: str) -> str | None:
        html = lxml.html.fromstring(response_text)
        attachments = html.xpath('//div[@class="unit-content--download"]/a/@href')
        return next(iter(attachments), None)

    def _extract_files_from_html(self, html_content: str) -> list[str]:
        """Extract file URLs from HTML content"""
        try:
            html = lxml.html.fromstring(html_content)
            # Look specifically for RAR files
            file_links = html.xpath('//a[contains(@href, ".rar")]/@href')
            
            # Convert relative URLs to absolute
            file_links = [f"{self.BASE_URL}{link}" if not link.startswith('http') else link 
                         for link in file_links]
            
            return list(set(file_links))  # Remove duplicates
        except Exception as e:
            logging.error(f"Error extracting files from HTML: {e}")
            return []

    def _download_html_files(self, file_urls: list[str], output_directory: str, unit_name: str) -> None:
        """Download files found in HTML content"""
        for url in file_urls:
            try:
                # Get the file name and extension from the URL
                original_name = url.split('/')[-1]
                name_parts = original_name.split('.')
                if len(name_parts) > 1:
                    extension = name_parts[-1].lower()
                    # Create a clean name from the unit name
                    clean_unit_name = unit_name.replace('_', ' ').strip()
                    # Create new filename with unit name and proper extension
                    new_filename = f"{clean_unit_name}.{extension}"
                    output_file = os.path.join(output_directory, new_filename)
                    
                    logging.info(f"Downloading file: {url}")
                    logging.info(f"Saving as: {new_filename}")
                    self._download(url=url, output_file=output_file)
                else:
                    logging.error(f"Could not determine file extension for: {url}")
            except Exception as e:
                logging.error(f"Error downloading file {url}: {e}")

    def download_course_videos(self, course_info: CourseInfo, max_threads: int = 1):
        course_link = course_info.link
        course_title = course_info.course.title
        chapters = course_info.chapters.chapters
        course_directory = os.path.join(self.output_path, sanitize_filename(course_title))
        if not os.path.exists(course_directory):
            logging.info(f"Creating course directory: {course_directory}")
            os.makedirs(course_directory, exist_ok=True)

        for i, chapter in enumerate(chapters):
            logging.info(f"Processing chapter: {chapter.title}")
            chapter_title = chapter.title
            chapter_slug = chapter.slug
            chapter_id = chapter.id

            chapter_directory = os.path.join(
                course_directory,
                f"{i + 1}_{sanitize_filename(chapter_title)}"
            )
            if not os.path.exists(chapter_directory):
                logging.info(f"Creating chapter directory: {chapter_directory}")
                os.makedirs(chapter_directory, exist_ok=True)
            chapter_url = f"{chapter_slug}-ch{chapter_id}"
            chpater_units = chapter.unit_set
            for j, unit in enumerate(chpater_units):
                try:
                    logging.info(f"Processing unit: {unit.title}")
                    unit_title: str = unit.title
                    unit_slug: str = unit.slug
                    unit_type: str = unit.type
                    unit_name: str = f"{j + 1}_{sanitize_filename(unit_title)}"

                    unit_url = f"{course_link}{chapter_url}/{unit_slug}/"
                    logging.info(f"Getting Page unit started: {unit_url}")
                    response = self.request(url=unit_url)
                    response.raise_for_status()
                    response_text = response.text
                    logging.info(f"Getting Page unit finished: {unit_url}")

                    # Handle attachments for all unit types
                    has_attachment: bool = unit.attachment
                    if has_attachment:
                        logging.info("Handling attachment")
                        self._handle_attachment(
                            response_text=response_text,
                            chapter_directory=chapter_directory,
                            unit_name=unit_name,
                        )

                    # Handle content based on unit type
                    if unit_type == "lecture":
                        # Handle video content and subtitles for lectures
                        logging.info("Handling video content for lecture")
                        has_subtitle: bool = True
                        if has_subtitle:
                            logging.info("Handling video subtitle")
                            self._handle_subtitle(
                                response_text=response_text,
                                chapter_directory=chapter_directory,
                                unit_name=unit_name,
                            )

                        logging.info("Handling video links")
                        self._handle_video(
                            response_text=response_text,
                            chapter_directory=chapter_directory,
                            unit_name=unit_name,
                        )
                    else:
                        # For non-lecture units (text, assignment, quiz)
                        logging.info(f"Saving {unit_type} content")
                        content_file = os.path.join(chapter_directory, f"{unit_name}.html")
                        with open(content_file, "w", encoding="utf-8") as f:
                            f.write(response_text)
                        logging.info(f"Saved {unit_type} content to {content_file}")
                        
                        # Extract and download RAR files from the HTML
                        file_urls = self._extract_files_from_html(response_text)
                        if file_urls:
                            logging.info(f"Found {len(file_urls)} RAR files in HTML content")
                            self._download_html_files(file_urls, chapter_directory, unit_name)

                    rnd = random.randint(0, 1)
                    logging.info(f"Sleeping for {rnd} seconds")
                    time.sleep(rnd)

                except Exception as e:
                    logging.error(f"Error in unit: {unit_title}")
                    logging.error(e)

                    rnd = random.randint(0, 60)
                    logging.info(f"Sleeping for {rnd} seconds")
                    time.sleep(rnd)

    def __del__(self):
        del self

    def _extract_download_urls(self, response_text: str) -> list[str]:
        """Extract all download URLs from HTML content"""
        try:
            html = lxml.html.fromstring(response_text)
            urls = []
            
            # Extract video URLs
            video_urls = html.xpath("//source/attribute::src")
            urls.extend(video_urls)
            
            # Extract subtitle URLs
            subtitle_urls = html.xpath('//track[@kind="subtitles"]/@src')
            urls.extend(subtitle_urls)
            
            # Extract attachment URLs
            attachment_urls = html.xpath('//div[@class="unit-content--download"]/a/@href')
            urls.extend(attachment_urls)
            
            # Extract RAR/ZIP file URLs
            file_urls = html.xpath('//a[contains(@href, ".rar") or contains(@href, ".zip")]/@href')
            urls.extend(file_urls)
            
            # Convert relative URLs to absolute
            urls = [f"{self.BASE_URL}{url}" if not url.startswith('http') else url 
                   for url in urls]
            
            return list(set(urls))  # Remove duplicates
        except Exception as e:
            logging.error(f"Error extracting download URLs: {e}")
            return []

    def save_download_urls(self, course_info: CourseInfo, output_path: str) -> None:
        """Save all download URLs to a file"""
        links_file = os.path.join(output_path, 'links.txt')
        with open(links_file, 'w', encoding='utf-8') as f:
            f.write("Course Download Links:\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Course Main Link: {course_info.link}\n\n")
            
            for chapter in course_info.chapters.chapters:
                f.write(f"\nChapter: {chapter.title}\n")
                f.write("-" * 30 + "\n")
                
                for unit in chapter.unit_set:
                    f.write(f"\nUnit: {unit.title}\n")
                    f.write(f"Type: {unit.type}\n")
                    
                    # Get the unit URL
                    chapter_url = f"{chapter.slug}-ch{chapter.id}"
                    unit_url = f"{course_info.link}{chapter_url}/{unit.slug}/"
                    f.write(f"Unit URL: {unit_url}\n")
                    
                    try:
                        # Get the page content
                        response = self.request(url=unit_url)
                        response.raise_for_status()
                        
                        # Extract download URLs
                        download_urls = self._extract_download_urls(response.text)
                        if download_urls:
                            f.write("\nDownload URLs:\n")
                            for url in download_urls:
                                f.write(f"{url}\n")
                    except Exception as e:
                        logging.error(f"Error getting URLs for unit {unit.title}: {e}")
                    
                    f.write("\n")

    def _handle_subtitle(
        self, response_text: str, chapter_directory: str, unit_name: str
    ) -> bool:
        res: bool = False
        subtitle_link = self._extract_subtitle_link(response_text)
        if subtitle_link:
            # Get the file extension from the URL
            ext = "vtt"  # Default to .vtt extension for subtitles
            
            # url is relative
            subtitle_url = f"{self.BASE_URL}{subtitle_link}"
            
            # Create a subfolder for the lecture
            base_name = os.path.splitext(unit_name)[0]
            lecture_folder = os.path.join(chapter_directory, base_name)
            os.makedirs(lecture_folder, exist_ok=True)
            
            # Create subtitle path in the lecture folder
            unit_subtitle_path = os.path.join(lecture_folder, f"{base_name}.{ext}")
            
            logging.info(f"Downloading subtitle started: {subtitle_url}")
            try:
                # Download the subtitle file
                response = self.client.get(subtitle_url)
                response.raise_for_status()
                
                # Save the subtitle content
                with open(unit_subtitle_path, 'wb') as f:
                    f.write(response.content)
                
                logging.info(f"Subtitle downloaded successfully to: {unit_subtitle_path}")
                res = True
            except Exception as e:
                logging.error(f"Error downloading subtitle: {e}")
                res = False

        else:
            logging.info("No subtitle found")

        return res

    def _handle_attachment(
        self, response_text: str, chapter_directory: str, unit_name: str
    ) -> bool:
        res: bool = False
        attachment_link = self._extract_attachment_link(response_text)
        if attachment_link:
            # url is not relative
            attachment_url = attachment_link
            attachment_name = attachment_url.split("?")[0].split("/")[-1]
            file_name = f"{sanitize_filename(attachment_name)}"

            unit_attachment_path = f"{chapter_directory}{os.sep}{unit_name}_{file_name}"
            logging.info(f"Downloading attachment started: {attachment_url}")
            res = self._download(
                url=attachment_url,
                output_file=unit_attachment_path,
            )
            logging.info(f"Downloading attachment finished: {attachment_url}")

        else:
            logging.info("No attachment found")
        return res

    def _handle_video(self, response_text: str, chapter_directory: str, unit_name: str):
        video_links = self._extract_video_link(response_text)
        logging.info(f"Found {len(video_links)} video links")
        try:
            logging.info("Trying to get hq video link")
            video_url = next((x for x in video_links if "hq" in x))
        except Exception as e:
            logging.error(f"error: {e}")
            logging.error(video_links)
            video_url = video_links[0]

        ext = video_url.split("?")[0].split(".")[-1]
        
        # Check if this lecture has a subtitle
        subtitle_link = self._extract_subtitle_link(response_text)
        if subtitle_link:
            # If there's a subtitle, use the lecture folder
            base_name = os.path.splitext(unit_name)[0]
            lecture_folder = os.path.join(chapter_directory, base_name)
            os.makedirs(lecture_folder, exist_ok=True)
            unit_video_path = os.path.join(lecture_folder, f"{base_name}.{ext}")
        else:
            # If no subtitle, save directly in chapter directory
            unit_video_path = os.path.join(chapter_directory, f"{unit_name}.{ext}")
            
        logging.info(f"Downloading video started: {video_url}")
        res: bool = self._download_video(
            video_url=video_url,
            output_file=unit_video_path,
        )
        logging.info(f"Downloading video finished: {video_url}")
        return res

    def download_courses_from_file(self, courses_file: str = "courses.txt") -> None:
        """
        Download multiple courses from a text file containing course URLs.
        Each URL should be on a new line in the file.
        
        Args:
            courses_file (str): Path to the file containing course URLs
        """
        if not os.path.exists(courses_file):
            logging.error(f"Courses file not found: {courses_file}")
            return

        with open(courses_file, 'r', encoding='utf-8') as f:
            course_urls = [line.strip() for line in f if line.strip()]

        if not course_urls:
            logging.error("No course URLs found in the file")
            return

        logging.info(f"Found {len(course_urls)} courses to download")
        
        for i, course_url in enumerate(course_urls, 1):
            try:
                logging.info(f"\nProcessing course {i}/{len(course_urls)}: {course_url}")
                
                # Crawl course info
                course_info = self.crawl_course_link(course_url)
                
                # Enroll in the course
                self.enroll_course_link(course_url)
                
                # Download course videos
                self.download_course_videos(course_info)
                
                # Save download URLs
                self.save_download_urls(course_info, self.output_path)
                
                logging.info(f"Successfully downloaded course: {course_info.course.title}")
                
                # Add a small delay between courses
                time.sleep(2)
                
            except Exception as e:
                logging.error(f"Error processing course {course_url}: {e}")
                continue
