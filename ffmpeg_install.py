import zipfile
import requests
import os
import subprocess
from tqdm import tqdm


def ffmpeg_install_windows():
    try:
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-6.1.1-essentials_build.zip"
        ffmpeg_zip_filename = "ffmpeg.zip"
        ffmpeg_extracted_folder = "ffmpeg"

        # Check if ffmpeg.zip already exists
        if os.path.exists(ffmpeg_zip_filename):
            os.remove(ffmpeg_zip_filename)

        # Download FFmpeg
        r = requests.get(ffmpeg_url, stream=True)
        total_size = int(r.headers.get("content-length", 0))
        with tqdm(total=total_size, unit="B", unit_scale=True) as progress_bar:
            with open(ffmpeg_zip_filename, "wb") as file:
                for data in r.iter_content(chunk_size=1024):
                    file.write(data)
                    progress_bar.update(len(data))

        # Check if the extracted folder already exists
        if os.path.exists(ffmpeg_extracted_folder):
            # Remove existing extracted folder and its contents
            for root, dirs, files in os.walk(ffmpeg_extracted_folder, topdown=False):
                for file in files:
                    os.remove(os.path.join(root, file))
                for dir in dirs:
                    os.rmdir(os.path.join(root, dir))
            os.rmdir(ffmpeg_extracted_folder)

        # Extract FFmpeg
        with zipfile.ZipFile(ffmpeg_zip_filename, "r") as zip_ref:
            zip_ref.extractall()
        os.remove("ffmpeg.zip")

        # Rename and move files
        os.rename(
            f"{ffmpeg_extracted_folder}-6.1.1-essentials_build", ffmpeg_extracted_folder
        )
        for file in os.listdir(os.path.join(ffmpeg_extracted_folder, "bin")):
            os.rename(
                os.path.join(ffmpeg_extracted_folder, "bin", file),
                os.path.join(".", file),
            )
        os.rmdir(os.path.join(ffmpeg_extracted_folder, "bin"))
        for file in os.listdir(os.path.join(ffmpeg_extracted_folder, "doc")):
            os.remove(os.path.join(ffmpeg_extracted_folder, "doc", file))
        for file in os.listdir(os.path.join(ffmpeg_extracted_folder, "presets")):
            os.remove(os.path.join(ffmpeg_extracted_folder, "presets", file))
        os.rmdir(os.path.join(ffmpeg_extracted_folder, "presets"))
        os.rmdir(os.path.join(ffmpeg_extracted_folder, "doc"))
        os.remove(os.path.join(ffmpeg_extracted_folder, "LICENSE"))
        os.remove(os.path.join(ffmpeg_extracted_folder, "README.txt"))
        os.rmdir(ffmpeg_extracted_folder)

        print(
            "FFmpeg installed successfully! Please restart your computer and then re-run the program."
        )
    except Exception as e:
        print(
            "An error occurred while trying to install FFmpeg. Please try again. Otherwise, please install FFmpeg manually and try again."
        )
        print(e)
        exit()


def ffmpeg_install_linux():
    try:
        out = subprocess.run(
            "apt",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout_msg = out.stdout

        if stdout_msg:
            # Deb System
            subprocess.run(
                "sudo apt update&&sudo apt install ffmpeg",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            # rpmSystem
            subprocess.run(
                (
                    "yum install epel-release -y && yum update -y && rpm --import http://li.nux.ro/download/nux/RPM-GPG-KEY-nux.ro  && rpm -Uvh http://li.nux.ro/download/nux/dextop/el7/x86_64/nux-dextop-release-0-5.el7.nux.noarch.rpm  &&  yum install ffmpeg -y"
                ),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    except Exception as e:
        print("An error occurred while trying to install FFmpeg.")
        print(e)
        exit()
    print("FFmpeg installed successfully! Please re-run the program.")
    exit()


def ffmpeg_install_mac():
    try:
        subprocess.run(
            "brew install ffmpeg",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print("Homebrew is not installed. ")
        exit()
    print("FFmpeg installed successfully! Please re-run the program.")
    exit()


def ffmpeg_install():
    try:
        # Try to run the FFmpeg command
        subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print("FFmpeg is installed!")
    except FileNotFoundError as e:
        print("FFmpeg is not installed.")
        resp = input(
            "We can try to automatically install it for you. Would you like to do that? (y/n): "
        )
        if resp.lower() == "y":
            print("Installing FFmpeg...")
            if os.name == "nt":
                ffmpeg_install_windows()
            elif os.name == "posix":
                ffmpeg_install_linux()
            elif os.name == "mac":
                ffmpeg_install_mac()
            else:
                print(
                    "Your OS is not supported. Please install FFmpeg manually and try again."
                )
                exit()
        else:
            print("Please install FFmpeg manually and try again.")
            exit()
    except Exception as e:
        print("ffmpeg install error,please propose issus for this project")
        print(e)
        raise e
