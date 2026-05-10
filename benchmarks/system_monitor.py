import argparse
import csv
import time
from datetime import datetime

import psutil

def monitor_system(duration: int, interval: int, output_file: str):
    print(f"Starting system monitor for {duration} seconds (interval: {interval}s)...")
    print(f"Logging to {output_file}")
    
    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "Timestamp", 
            "CPU_Percent", 
            "Memory_Percent", 
            "Disk_Read_MB", 
            "Disk_Write_MB", 
            "Net_Sent_MB", 
            "Net_Recv_MB"
        ])
        
        start_time = time.time()
        
        disk_io_start = psutil.disk_io_counters()
        net_io_start = psutil.net_io_counters()
        
        while time.time() - start_time < duration:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            
            disk_io = psutil.disk_io_counters()
            disk_read_mb = (disk_io.read_bytes - disk_io_start.read_bytes) / (1024 * 1024)
            disk_write_mb = (disk_io.write_bytes - disk_io_start.write_bytes) / (1024 * 1024)
            
            net_io = psutil.net_io_counters()
            net_sent_mb = (net_io.bytes_sent - net_io_start.bytes_sent) / (1024 * 1024)
            net_recv_mb = (net_io.bytes_recv - net_io_start.bytes_recv) / (1024 * 1024)
            
            writer.writerow([
                timestamp, cpu, mem, 
                round(disk_read_mb, 2), round(disk_write_mb, 2), 
                round(net_sent_mb, 2), round(net_recv_mb, 2)
            ])
            
            time.sleep(interval)
            
    print("Monitoring complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vMachine System Resource Monitor")
    parser.add_argument("--duration", type=int, default=300, help="Duration to monitor in seconds")
    parser.add_argument("--interval", type=int, default=2, help="Interval between measurements in seconds")
    parser.add_argument("--output", type=str, default="system_metrics.csv", help="Output CSV file name")
    
    args = parser.parse_args()
    monitor_system(args.duration, args.interval, args.output)
