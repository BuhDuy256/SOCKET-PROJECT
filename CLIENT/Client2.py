import socket
import threading
from tqdm import tqdm
import hashlib

CHUNK_SIZE = 1024  # 1 KB

def calculate_checksum(data):

    hash_obj = hashlib.sha256()
    hash_obj.update(data)
    return hash_obj.hexdigest()

def download_chunk(server_ip, server_port, file_name, start, end, part_index, progress_bar):

    try:
        # Connect to server
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((server_ip, server_port))
        
      
        request = f"GET {file_name} {start} {end}\n"
        client_socket.send(request.encode())
        
        # Save data to file
        with open(f"part_{part_index}.tmp", "wb") as part_file:
            total_bytes_received = 0
            while total_bytes_received < (end - start):
                # Receive data
                data = client_socket.recv(CHUNK_SIZE)
                if not data:
                    break
                total_bytes_received += len(data)
                
                # Receive CHECKSUM
                checksum = client_socket.recv(64).decode()
                
                # Check CHECKSUM
                if calculate_checksum(data) != checksum:
                    raise ValueError(f"CHECK SUM ERROR AT {part_index}")
                
                part_file.write(data)
                # Update progress bar
                progress_bar.update(len(data))
        
        client_socket.close()
    except Exception as e:
        print(f"Error at thread {part_index}: {e}")

def merge_files(file_name, num_parts):
    
    with open(file_name, "wb") as output_file:
        for i in range(num_parts):
            part_file = f"part_{i}.tmp"
            with open(part_file, "rb") as pf:
                output_file.write(pf.read())

def main():
    # Cấu hình
    server_ip = socket.gethostbyname(socket.gethostname())       
    server_port = 5000           
    file_name = "100MB.zip" 
    num_threads = 4              
    

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((server_ip, server_port))
    client_socket.send(f"SIZE {file_name}\n".encode())
    file_size = int(client_socket.recv(1024).decode())
    client_socket.close()

    print(f"Kích thước tệp: {file_size} bytes")
    

    chunk_size = file_size // num_threads
    threads = []
    progress_bars = []


    for i in range(num_threads):
        start = i * chunk_size
        end = start + chunk_size if i < num_threads - 1 else file_size
        progress_bar = tqdm(total=(end - start), desc=f"Thread {i}", unit="B", unit_scale=True)
        progress_bars.append(progress_bar)
        thread = threading.Thread(target=download_chunk, args=(server_ip, server_port, file_name, start, end, i, progress_bar))
        threads.append(thread)
        thread.start()

    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    for progress_bar in progress_bars:
        progress_bar.close()
    

    print("Merge files...")
    merge_files("downloaded_" + file_name, num_threads)
    print("Done!")

if __name__ == "__main__":
    main()
