#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import argparse
from playwright.sync_api import sync_playwright

PANEL_URL = 'http://172.17.60.248:29768/hzwpc1hf'
USERNAME = 'b1wa1xhx'
PASSWORD = 'ND0SgUTidJpd'

# 要巡检的关键路由
TEST_PAGES = [
    {'name': '首页', 'url': 'http://172.17.60.248:29768/'},
    {'name': '网站管理', 'url': 'http://172.17.60.248:29768/site'},
    {'name': '文件管理', 'url': 'http://172.17.60.248:29768/files'},
    {'name': '计划任务', 'url': 'http://172.17.60.248:29768/crontab'},
    {'name': '安全管理', 'url': 'http://172.17.60.248:29768/firewall'},
    {'name': '软件商店', 'url': 'http://172.17.60.248:29768/soft'},
    {'name': '面板设置', 'url': 'http://172.17.60.248:29768/setting'},
    {'name': '面板日志', 'url': 'http://172.17.60.248:29768/logs'}
]

def run_regression_test(headful=False):
    reports = {
        'summary': {
            'total_warnings': 0,
            'total_errors': 0,
            'pass': True
        },
        'pages': []
    }
    
    with sync_playwright() as p:
        print("[*] 正在启动 Playwright 浏览器...")
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context()
        page = context.new_page()

        # 收集控制台输出和 JS Error
        current_page_findings = {'warnings': [], 'errors': []}

        def handle_console(msg):
            text = msg.text
            if 'JQMIGRATE' in text or 'jquery' in text.lower():
                # 记录 jQuery Migrate 警告或其它 jQuery 相关信息
                current_page_findings['warnings'].append(f"[{msg.type}] {text}")
                print(f"  [!] Console Warning: {text}")

        def handle_pageerror(err):
            current_page_findings['errors'].append(err.message)
            print(f"  [-] JS Error: {err.message}")

        page.on("console", handle_console)
        page.on("pageerror", handle_pageerror)

        # 1. 访问并测试登录页
        print(f"[*] 访问登录页面: {PANEL_URL}")
        try:
            page.goto(PANEL_URL, timeout=15000)
            page.wait_for_timeout(2000)  # 等待加载完毕
        except Exception as e:
            print(f"[-] 页面访问超时/失败: {PANEL_URL}, 错误: {e}")
            reports['pages'].append({
                'name': '登录页',
                'url': PANEL_URL,
                'status': 'FAIL',
                'warnings': [],
                'errors': [str(e)]
            })
            browser.close()
            return reports

        reports['pages'].append({
            'name': '登录页',
            'url': PANEL_URL,
            'status': 'PASS' if not current_page_findings['errors'] else 'FAIL',
            'warnings': list(current_page_findings['warnings']),
            'errors': list(current_page_findings['errors'])
        })
        
        # 2. 执行自动登录
        print("[*] 输入凭据进行登录...")
        current_page_findings['warnings'].clear()
        current_page_findings['errors'].clear()
        
        try:
            # 输入用户名密码
            page.fill('input[name="username"]', USERNAME)
            page.fill('input[name="password"]', PASSWORD)
            
            # 检测是否有验证码输入框，若有则等待用户在 terminal 中手动输入或截屏输入 (御风面板通常如果登录次数少是没有验证码的)
            yzm_visible = page.locator('#mw_yzm img').is_visible()
            if yzm_visible:
                print("[!] 登录页检测到验证码！请输入验证码的值：")
                code_val = input("请输入登录验证码: ")
                page.fill('input[name="code"]', code_val)
            
            # 点击登录
            page.click('#login-button')
            
            # 等待首页加载，通常会出现侧边栏菜单
            page.wait_for_selector('.menu', timeout=15000)
            print("[+] 登录成功，已进入管理面板首页！")
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[-] 登录失败/超时: {e}")
            try:
                page.screenshot(path="login_error.png")
                print("[+] 已保存异常时刻截图为: login_error.png")
            except Exception as se:
                print(f"[-] 截图失败: {se}")
            reports['summary']['pass'] = False
            browser.close()
            return reports

        # 3. 循环测试所有主要页面（通过侧边栏点击以确保测试 Pjax 流程）
        for item in TEST_PAGES:
            name = item['name']
            url = item['url']
            print(f"[*] 巡检页面: {name} ({url})")
            
            current_page_findings['warnings'].clear()
            current_page_findings['errors'].clear()
            
            try:
                # 优先寻找左侧菜单项并点击
                # 菜单的 href 通常对应 /site, /files 等
                target_path = url.split(':29768')[-1] # 提取相对路径
                menu_selector = f".menu a[href='{target_path}']"
                
                if page.locator(menu_selector).is_visible():
                    print(f"  [+] 模拟点击侧边栏菜单: {name}")
                    page.click(menu_selector)
                else:
                    # 如果菜单项不可见/没找到，直接跳转
                    print(f"  [!] 菜单未找到，直接跳转: {url}")
                    page.goto(url)
                
                page.wait_for_timeout(3000) # 充分等待页面渲染和脚本执行
            except Exception as e:
                print(f"  [-] 巡检异常: {e}")
                current_page_findings['errors'].append(str(e))
            
            status = 'PASS'
            if current_page_findings['errors']:
                status = 'FAIL'
                reports['summary']['total_errors'] += len(current_page_findings['errors'])
            if current_page_findings['warnings']:
                reports['summary']['total_warnings'] += len(current_page_findings['warnings'])
                if status == 'PASS':
                    status = 'WARN'

            reports['pages'].append({
                'name': name,
                'url': url,
                'status': status,
                'warnings': list(current_page_findings['warnings']),
                'errors': list(current_page_findings['errors'])
            })

        browser.close()
        
    reports['summary']['pass'] = (reports['summary']['total_errors'] == 0 and reports['summary']['total_warnings'] == 0)
    return reports

def main():
    parser = argparse.ArgumentParser(description='jQuery 升级回归测试')
    parser.add_argument('--head', action='store_true', help='使用 headful 有头模式运行')
    args = parser.parse_args()

    reports = run_regression_test(headful=args.head)
    
    # 写入 JSON 报告
    report_file = 'jq_upgrade_test_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)
        
    print("\n" + "="*50)
    print(f"[!] 测试结束。生成报告: {report_file}")
    print(f"[!] 汇总: 黄色兼容警告: {reports['summary']['total_warnings']} 处，JS 错误: {reports['summary']['total_errors']} 处")
    
    if reports['summary']['pass']:
        print("[+] 恭喜！全页面通过测试，零报错零警告！")
    else:
        print("[-] 检测到警告或报错，请查阅报告以进行修复。")
        for p in reports['pages']:
            if p['status'] != 'PASS':
                print(f"页面: {p['name']} ({p['status']})")
                for w in p['warnings']:
                    print(f"  - 警告: {w}")
                for e in p['errors']:
                    print(f"  - 错误: {e}")

if __name__ == '__main__':
    main()
