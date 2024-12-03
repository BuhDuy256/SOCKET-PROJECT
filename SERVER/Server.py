import os
import threading
import time

# Hàm chuyển đổi kích thước tệp từ byte thành chuỗi có đơn vị (MB, GB, ...)
def format_size(size_in_bytes):
    if size_in_bytes >= 1024 * 1024 * 1024:  # GB
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f}GB"
    elif size_in_bytes >= 1024 * 1024:  # MB
        return f"{size_in_bytes / (1024 * 1024):.2f}MB"
    elif size_in_bytes >= 1024:  # KB
        return f"{size_in_bytes / 1024:.2f}KB"
    else:  # Byte
        return f"{size_in_bytes}B"

# Danh sách các tệp bị cấm
blocked_files = ['Server.py', 'allow_download.txt']

# Hàm chuyển đổi kích thước tệp từ chuỗi có đơn vị (như '5MB') thành byte
def parse_size(size_str):
    size_str = size_str.strip().upper()
    if size_str.endswith("MB"):
        return int(float(size_str[:-2])) * 1024 * 1024  # Chuyển MB thành byte
    elif size_str.endswith("GB"):
        return int(float(size_str[:-2])) * 1024 * 1024 * 1024  # Chuyển GB thành byte
    elif size_str.endswith("KB"):
        return int(float(size_str[:-2])) * 1024  # Chuyển KB thành byte
    elif size_str.isdigit():
        return int(size_str)  # Trường hợp không có đơn vị, giả sử là byte
    else:
        raise ValueError(f"Invalid size format: {size_str}")

# Đọc danh sách tệp từ allow_download.txt
def read_allow_list(filepath="allow_download.txt"):
    allow_list = {}
    try:
        with open(filepath, 'r') as file:
            for line in file:
                filename, size_str = line.strip().split()
                size = parse_size(size_str)  # Sử dụng hàm parse_size để chuyển đổi kích thước
                allow_list[filename] = size
    except IOError as e:
        print(f"Error opening file {filepath}: {e}")
    except ValueError as e:
        print(f"Error parsing size: {e}")
    return allow_list

# Cập nhật kích thước tệp trong allow_download.txt
def update_file_size(filename, new_size, filepath="allow_download.txt"):
    allow_list = read_allow_list(filepath)
    if filename in allow_list:
        allow_list[filename] = new_size
    try:
        with open(filepath, 'w') as file:
            for fname, size in allow_list.items():
                # Ghi vào file với kích thước đã được chuyển đổi sang MB, GB, ...
                file.write(f"{fname} {format_size(size)}\n")
    except IOError as e:
        print(f"Error updating file {filepath}: {e}")

# Xóa tệp khỏi allow_download.txt
def remove_file(filename, filepath='allow_download.txt'):
    allow_list = read_allow_list(filepath)
    if filename in allow_list:
        del allow_list[filename]
    try:
        with open(filepath, 'w') as file:
            for fname, size in allow_list.items():
                file.write(f"{fname} {format_size(size)}\n")
    except IOError as e:
        print(f"Error removing file {filename} from {filepath}: {e}")

# Thêm tệp vào allow_download.txt
def add_file(filename, size, filepath='allow_download.txt'):
    if filename in blocked_files:
        print(f"File {filename} is blocked and cannot be added.")
        return
    allow_list = read_allow_list(filepath)
    allow_list[filename] = size
    try:
        with open(filepath, 'w') as file:
            for fname, size in allow_list.items():
                file.write(f"{fname} {format_size(size)}\n")
    except IOError as e:
        print(f"Error adding file {filename} to {filepath}: {e}")

# Quét thư mục hiện tại và cập nhật allow_download.txt
def update_allow_download_from_folder(directory=".", filepath="allow_download.txt"):
    # Lấy danh sách tệp trong thư mục hiện tại
    current_files = {}
    try:
        current_files = {f: os.path.getsize(os.path.join(directory, f)) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and f not in blocked_files}
    except OSError as e:
        print(f"Error accessing directory {directory}: {e}")

    # Đọc danh sách tệp hiện tại từ allow_download.txt
    allow_list = read_allow_list(filepath)

    # Duyệt qua danh sách tệp hiện tại trong thư mục
    for filename in list(allow_list.keys()):  # Duyệt qua bản sao danh sách (copy) để tránh lỗi khi xóa
        if filename not in current_files:
            # Nếu tệp không tồn tại trong thư mục, xóa khỏi allow_download.txt
            print(f"Removing {filename} from allow_download.txt because it's no longer in the folder.")
            remove_file(filename, filepath)

    # Duyệt qua danh sách các tệp trong thư mục và cập nhật hoặc thêm tệp vào allow_download.txt
    for filename, size in current_files.items():
        if filename in allow_list:
            if allow_list[filename] != size:
                # Nếu kích thước tệp thay đổi, cập nhật kích thước
                print(f"Updating size of {filename} to {size} in allow_download.txt.")
                update_file_size(filename, size, filepath)
        else:
            # Nếu tệp chưa có trong allow_download.txt, thêm vào
            print(f"Adding {filename} to allow_download.txt.")
            add_file(filename, size, filepath)

# Hàm sẽ chạy mỗi 5 giây để cập nhật allow_download.txt
def update_periodically():
    while True:
        # Cập nhật allow_download.txt từ thư mục
        update_allow_download_from_folder()
        # Đợi 5 giây trước khi quét lại thư mục
        time.sleep(5)

# Khởi động thread để cập nhật định kỳ
def start_updating_thread():
    update_thread = threading.Thread(target=update_periodically)
    update_thread.daemon = True  # Đảm bảo thread này sẽ dừng khi chương trình kết thúc
    update_thread.start()

# Ví dụ sử dụng:
if __name__ == "__main__":
    # Bắt đầu thread cập nhật allow_download.txt mỗi 5 giây
    start_updating_thread()

    # Các phần mã khác của server hoặc chương trình có thể tiếp tục chạy
    while True:
        time.sleep(1)  # Giữ chương trình hoạt động
