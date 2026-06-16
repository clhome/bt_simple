import time
import requests

# 待测试的 GitHub 原始资源链接
target_url = "https://github.com/openssl/openssl/releases/download/openssl-3.5.5/openssl-3.5.5.tar.gz"

# 收集的中转站列表（结尾带 /）
proxies = [
    "https://gh-proxy.com/",
    "https://cors.zme.ink/",
    "https://gh.ddlc.top/",
    "https://ghproxy.net/",
]

def test_proxy_speed(proxy_url, target, max_duration=60):
    # 拼接最终的下载链接
    download_url = f"{proxy_url}{target}"
    print(f"正在测试: {proxy_url} ...")
    
    try:
        start_time = time.time()
        # Stream=True 允许流式下载，避免直接将大文件加载到内存中
        response = requests.get(download_url, stream=True, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            return None
            
        downloaded_bytes = 0
        last_print_time = time.time()
        
        # 每次读取 1024 字节 (1KB)
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                downloaded_bytes += len(chunk)
                
                # 每过 1 分钟（max_duration）就强行停止
                elapsed_time = time.time() - start_time
                if elapsed_time >= max_duration:
                    break
                    
        actual_duration = time.time() - start_time
        
        # 计算平均速度 (MB/s)
        downloaded_mb = downloaded_bytes / (1024 * 1024)
        avg_speed = downloaded_mb / actual_duration
        
        print(f"✅ 完成测试! 已下载: {downloaded_mb:.2f} MB, 耗时: {actual_duration:.1f} 秒")
        return avg_speed

    except requests.exceptions.RequestException as e:
        print(f"❌ 连接超时或出错")
        return None

if __name__ == "__main__":
    results = {}
    
    print("====== 开始测试 GitHub 中转站下载速度 ======")
    for proxy in proxies:
        speed = test_proxy_speed(proxy, target_url, max_duration=60)
        if speed is not None:
            results[proxy] = speed
        print("-" * 50)
        
    print("\n====== 最终速度排名 ======")
    # 按速度从大到小排序
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    
    for rank, (proxy, speed) in enumerate(sorted_results, 1):
        print(f"第 {rank} 名: {proxy} ---> 平均速度: {speed:.2f} MB/s")