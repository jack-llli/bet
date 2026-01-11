#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚球水位实时监控系统 v4.1
- 修复登录按钮问题
- 修复球队识别
- 修复主客队水位归类
"""

from selenium import webdriver
from selenium. webdriver.common.by import By
from selenium.webdriver.support. ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium. common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
import time
import pickle
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
from datetime import datetime
import re
import json
import os

# ================== 配置 ==================
URL = "https://mos055.com/"
USERNAME = "LJJ123123"
PASSWORD = "zz66688899"
COOKIES_FILE = "mos055_cookies.pkl"
CONFIG_FILE = "bet_config.json"

# ================== 盘口布局配置 ==================
LAYOUT_CONFIG = {
    '让球': (420, 520),
    '大/小': (520, 620),
    '独赢': (620, 740),
    '让球上半场': (740, 840),
    '大/小上半场': (840, 940),
    '独赢上半场': (940, 1060),
    '下个进球': (1060, 1160),
    '双方球队进球': (1160, 1280),
}

BET_TYPES_ORDER = ['让球', '大/小', '独赢', '让球上半场', '大/小上半场', '独赢上半场', '下个进球', '双方球队进球']


class BettingBot:
    """投注机器人核心类"""
    
    def __init__(self):
        self.driver = None
        self. is_running = False
        self.is_logged_in = False
        self.wait = None
        self.auto_bet_enabled = False
        self.bet_amount = 2
        self. bet_history = []
        self.current_matches = []
        self. odds_threshold = 1.80
        self.raw_data = None

    def setup_driver(self, headless=False):
        """初始化浏览器"""
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        if headless:
            options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 60)

        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            '''
        })

    def handle_password_popup(self, log_callback):
        """处理简易密码弹窗"""
        log_callback("检测并处理简易密码弹窗...")

        for attempt in range(15):
            try:
                popup_visible = self.driver.execute_script("""
                    var popup = document.getElementById('c_alert_modify');
                    if (popup) {
                        var style = window.getComputedStyle(popup);
                        return popup.offsetWidth > 0 && popup. offsetHeight > 0 &&
                               style.display !== 'none' && style. visibility !== 'hidden';
                    }
                    return false;
                """)

                if not popup_visible:
                    has_popup_text = self.driver.execute_script("""
                        return document.body.innerText.includes('简易密码') ||
                               document.body. innerText.includes('快速登入');
                    """)
                    if not has_popup_text:
                        log_callback("✓ 弹窗已关闭或不存在")
                        return True

                result = self.driver.execute_script("""
                    var elements = document.querySelectorAll('div, button, span');
                    for (var elem of elements) {
                        if (elem.innerText.trim() === '否' &&
                            elem. offsetWidth > 0 && elem.offsetHeight > 0) {
                            elem.click();
                            return {success: true};
                        }
                    }
                    return {success: false};
                """)
                if result.get('success'):
                    log_callback(f"  第{attempt+1}次点击成功")
                    time.sleep(2)
                    continue

                time.sleep(1)
            except: 
                time.sleep(1)

        return False

    def wait_for_matches_to_load(self, log_callback):
        """等待比赛数据加载"""
        log_callback("\n⏳ 等待比赛数据加载...")

        for attempt in range(10):
            time.sleep(2)
            
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(1)

            has_matches = self.driver.execute_script("""
                var text = document.body.innerText || '';
                return text.includes('让球') || text.includes('独赢') || 
                       text.includes('联赛') || text.includes('Esports');
            """)

            if has_matches:
                log_callback(f"✓ 检测到比赛数据 (尝试 {attempt + 1}/10)")
                time.sleep(2)
                return True

            log_callback(f"  尝试 {attempt + 1}/10 - 等待中...")

        log_callback("⚠️ 等待超时，继续尝试获取数据")
        return False

    def login(self, username, password, log_callback):
        """登录 - 修复版"""
        try:
            log_callback("正在访问登录页面...")
            self.driver.get(URL)
            time.sleep(8)
            
            # ========== 方法1: 使用ID查找 ==========
            log_callback("尝试查找登录表单...")
            
            # 输入用户名
            username_filled = False
            try:
                username_field = self.wait.until(EC.presence_of_element_located((By.ID, "usr")))
                self.driver.execute_script("arguments[0].value = arguments[1];", username_field, username)
                username_filled = True
                log_callback(f"✓ 已输入用户名: {username}")
            except: 
                log_callback("  ID='usr' 未找到，尝试其他方式...")
            
            if not username_filled:
                # 备用方法：使用JavaScript查找
                result = self.driver.execute_script(f"""
                    var inputs = document.querySelectorAll('input');
                    for(var i=0; i<inputs.length; i++){{
                        var input = inputs[i];
                        var type = input.type || '';
                        var placeholder = input.placeholder || '';
                        var name = input.name || '';
                        var id = input.id || '';
                        
                        if(type === 'text' && (placeholder. includes('用户') || placeholder.includes('帐号') || 
                           placeholder.includes('账号') || name.includes('usr') || name.includes('user') ||
                           id.includes('usr') || id.includes('user'))){{
                            input.value = '{username}';
                            input. dispatchEvent(new Event('input', {{bubbles: true}}));
                            return {{success: true, method: 'js_search'}};
                        }}
                    }}
                    // 如果没找到，尝试第一个text输入框
                    for(var i=0; i<inputs.length; i++){{
                        if(inputs[i].type === 'text' && inputs[i].offsetWidth > 0){{
                            inputs[i]. value = '{username}';
                            inputs[i].dispatchEvent(new Event('input', {{bubbles: true}}));
                            return {{success: true, method:  'first_text'}};
                        }}
                    }}
                    return {{success:  false}};
                """)
                if result and result.get('success'):
                    log_callback(f"✓ 已输入用户名 (方法:  {result.get('method')})")
                    username_filled = True
                else:
                    log_callback("✗ 无法找到用户名输入框")
                    return False
            
            # 输入密码
            password_filled = False
            try: 
                password_field = self.wait.until(EC.presence_of_element_located((By.ID, "pwd")))
                self.driver.execute_script("arguments[0].value = arguments[1];", password_field, password)
                password_filled = True
                log_callback("✓ 已输入密码")
            except:
                log_callback("  ID='pwd' 未找到，尝试其他方式...")
            
            if not password_filled: 
                result = self.driver.execute_script(f"""
                    var inputs = document.querySelectorAll('input[type="password"]');
                    for(var i=0; i<inputs.length; i++){{
                        if(inputs[i].offsetWidth > 0){{
                            inputs[i].value = '{password}';
                            inputs[i].dispatchEvent(new Event('input', {{bubbles: true}}));
                            return {{success: true}};
                        }}
                    }}
                    return {{success:  false}};
                """)
                if result and result.get('success'):
                    log_callback("✓ 已输入密码 (备用方法)")
                    password_filled = True
                else:
                    log_callback("✗ 无法找到密码输入框")
                    return False
            
            time.sleep(1)
            
            # ========== 点击登录按钮 - 多种方法 ==========
            log_callback("尝试点击登录按钮...")
            login_clicked = False
            
            # 方法1: 通过ID
            try:
                login_btn = self.driver.find_element(By.ID, "btn_login")
                if login_btn. is_displayed():
                    login_btn.click()
                    login_clicked = True
                    log_callback("✓ 已点击登录按钮 (ID='btn_login')")
            except:
                pass
            
            # 方法2: 通过class
            if not login_clicked:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.btn_login, . login-btn, .btn-login")
                    for btn in buttons:
                        if btn. is_displayed():
                            btn.click()
                            login_clicked = True
                            log_callback("✓ 已点击登录按钮 (CSS)")
                            break
                except:
                    pass
            
            # 方法3: 通过文本内容
            if not login_clicked:
                try:
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        text = btn.text.strip()
                        if text in ['登录', '登入', '立即登录', 'Login', '登 录']:
                            if btn.is_displayed():
                                btn.click()
                                login_clicked = True
                                log_callback(f"✓ 已点击登录按钮 (文本='{text}')")
                                break
                except:
                    pass
            
            # 方法4: JavaScript查找并点击
            if not login_clicked:
                result = self.driver.execute_script("""
                    // 查找登录按钮
                    var selectors = [
                        '#btn_login',
                        'button[type="submit"]',
                        '. btn_login',
                        '.login-btn',
                        'button.login',
                        'input[type="submit"]'
                    ];
                    
                    for(var i=0; i<selectors.length; i++){
                        var elem = document.querySelector(selectors[i]);
                        if(elem && elem.offsetWidth > 0){
                            elem.click();
                            return {success: true, selector: selectors[i]};
                        }
                    }
                    
                    // 通过文本查找
                    var allElements = document.querySelectorAll('button, div, span, a, input');
                    var loginTexts = ['登录', '登入', '立即登录', 'Login', '登 录', '确定'];
                    
                    for(var i=0; i<allElements.length; i++){
                        var el = allElements[i];
                        var text = (el.innerText || el.value || '').trim();
                        
                        for(var j=0; j<loginTexts.length; j++){
                            if(text === loginTexts[j] && el.offsetWidth > 0 && el.offsetHeight > 0){
                                el.click();
                                return {success: true, text: text};
                            }
                        }
                    }
                    
                    return {success: false};
                """)
                
                if result and result.get('success'):
                    login_clicked = True
                    if result.get('selector'):
                        log_callback(f"✓ 已点击登录按钮 (JS:  {result.get('selector')})")
                    else:
                        log_callback(f"✓ 已点击登录按钮 (JS文本: {result.get('text')})")
            
            # 方法5: 模拟回车
            if not login_clicked:
                log_callback("  尝试使用回车键登录...")
                try:
                    from selenium.webdriver.common.keys import Keys
                    password_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
                    for inp in password_inputs:
                        if inp.is_displayed():
                            inp.send_keys(Keys.RETURN)
                            login_clicked = True
                            log_callback("✓ 已发送回车键")
                            break
                except:
                    pass
            
            if not login_clicked:
                log_callback("✗ 无法找到或点击登录按钮")
                # 打印页面上所有按钮信息用于调试
                self.driver.execute_script("""
                    console.log('=== 页面按钮调试 ===');
                    var buttons = document.querySelectorAll('button, input[type="submit"], . btn');
                    buttons.forEach(function(btn, idx){
                        console.log(idx + ': ' + btn.tagName + ' | id=' + btn.id + ' | class=' + btn.className + ' | text=' + btn.innerText);
                    });
                """)
                return False
            
            # 等待登录响应
            log_callback("\n等待登录响应...")
            time.sleep(10)
            
            # 处理弹窗
            self.handle_password_popup(log_callback)
            time.sleep(3)
            
            # 等待主页面加载
            log_callback("\n等待主页面加载...")
            for i in range(10):
                time.sleep(5)
                elapsed = (i + 1) * 5
                log_callback(f"  已等待 {elapsed} 秒...")
                
                # 检查是否登录成功
                is_logged = self.driver.execute_script("""
                    return document.body.innerText.includes('滚球') || 
                           document.body.innerText.includes('余额') ||
                           document.body.innerText.includes('账户');
                """)
                if is_logged:
                    log_callback("✓ 检测到登录成功")
                    break

            log_callback(f"\n当前URL: {self.driver.current_url}")

            # 保存Cookies
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "wb") as f:
                pickle.dump(cookies, f)
            log_callback("✓ Cookies 已保存")

            # 进入滚球页面
            log_callback("\n进入滚球页面...")
            time.sleep(3)

            click_result = self.driver.execute_script("""
                var elements = document.querySelectorAll('*');
                for (var elem of elements) {
                    var text = (elem.textContent || '').trim();
                    var visible = elem.offsetWidth > 0 && elem.offsetHeight > 0;
                    if (visible && text === '滚球') {
                        elem.scrollIntoView({behavior: 'smooth', block:  'center'});
                        elem.click();
                        return {success: true};
                    }
                }
                return {success: false};
            """)

            if click_result. get('success'):
                log_callback("✓ 已点击滚球")

            log_callback("等待滚球页面加载...")
            time.sleep(10)

            self.wait_for_matches_to_load(log_callback)

            self.is_logged_in = True
            log_callback("\n✓ 登录流程完成！")
            return True

        except Exception as e:
            log_callback(f"\n✗ 登录失败:  {str(e)}")
            import traceback
            log_callback(traceback.format_exc())
            return False

    def get_raw_page_data(self):
        """获取页面所有原始数据"""
        try: 
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(0.3)
            self.driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(0.3)
            self.driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(0.5)

            raw_data = self.driver.execute_script("""
                function getRawPageData() {
                    var elements = [];
                    var allElements = document.querySelectorAll('*');
                    
                    allElements.forEach(function(elem) {
                        try {
                            var rect = elem.getBoundingClientRect();
                            if (rect.width <= 0 || rect.height <= 0) return;
                            if (rect.width > 500 || rect.height > 100) return;
                            if (rect.y < 50 || rect.y > 3000) return;
                            if (rect.x < 0 || rect.x > 1600) return;
                            
                            var text = '';
                            for (var i = 0; i < elem.childNodes.length; i++) {
                                if (elem.childNodes[i]. nodeType === 3) {
                                    text += elem.childNodes[i].textContent;
                                }
                            }
                            text = text.trim();
                            
                            if (! text && elem.childNodes.length === 0) {
                                text = (elem.textContent || '').trim();
                            }
                            
                            if (! text || text. length > 60) return;
                            if ((text.match(/\\n/g) || []).length > 2) return;
                            
                            elements.push({
                                text: text,
                                x: Math.round(rect.x),
                                y: Math.round(rect. y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                tag: elem.tagName
                            });
                        } catch(e) {}
                    });
                    
                    var seen = new Set();
                    var uniqueElements = [];
                    elements.forEach(function(e) {
                        var key = e.text + '_' + Math.round(e.x/5)*5 + '_' + Math. round(e.y/5)*5;
                        if (!seen.has(key)) {
                            seen.add(key);
                            uniqueElements.push(e);
                        }
                    });
                    
                    uniqueElements.sort(function(a, b) {
                        if (Math.abs(a.y - b.y) < 10) return a.x - b.x;
                        return a.y - b.y;
                    });
                    
                    return {
                        elements: uniqueElements,
                        total: uniqueElements.length,
                        timestamp: new Date().toISOString()
                    };
                }
                return getRawPageData();
            """)

            self.raw_data = raw_data
            return raw_data
        except Exception as e:
            return {'elements': [], 'total': 0, 'error': str(e)}

    def analyze_raw_data(self, raw_data, log_callback=None):
        """分析原始数据，提取比赛信息"""
        if not raw_data or not raw_data.get('elements'):
            return {'matches': [], 'totalOdds': 0}

        elements = raw_data['elements']

        odds_pattern = re.compile(r'^\d{1,2}\.\d{1,2}$')
        handicap_pattern = re.compile(r'^[+-]?\d+/?\d*\. ?\d*$')
        time_pattern = re.compile(r'(上半场|下半场|中场|半场)\s*\d+:\d+|\d+:\d+')
        score_pattern = re.compile(r'^\d{1,2}$')
        league_pattern = re.compile(r'(联赛|杯|甲组|超级|Esports|FIFA|女)', re.IGNORECASE)

        exclude_keywords = ['让球', '大小', '大/小', '独赢', '进球', '单双', '单/双', '半场',
                           '上半场', '下半场', '主', '客', '和', '大', '小', '是', '否', '无',
                           '队伍', '双方', '角球', '罚牌', '波胆', '主要玩法']

        match_starts = []
        for elem in elements:
            if time_pattern.search(elem['text']) and elem['x'] < 250:
                is_duplicate = False
                for ms in match_starts:
                    if abs(ms['y'] - elem['y']) < 60:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    match_starts.append({'time': elem['text'], 'y': elem['y'], 'x': elem['x']})

        match_starts.sort(key=lambda x: x['y'])

        matches = []
        total_odds_count = 0

        for idx, match_start in enumerate(match_starts):
            start_y = match_start['y'] - 40
            end_y = match_starts[idx + 1]['y'] - 30 if idx + 1 < len(match_starts) else start_y + 180

            match_elements = [e for e in elements if start_y <= e['y'] <= end_y]

            match = {
                'id': idx + 1,
                'league': '',
                'time': match_start['time'],
                'team1': '', 'team2': '',
                'score1': '', 'score2': '',
                'team1_y': 0, 'team2_y': 0,
                'odds':  {bt: {'handicap': '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
            }

            for elem in elements:
                if elem['y'] < start_y and league_pattern.search(elem['text']) and len(elem['text']) < 50:
                    match['league'] = elem['text']

            team_candidates = []
            for elem in match_elements:
                text = elem['text']. strip()
                x = elem['x']

                if x < 50 or x > 280:
                    continue
                if len(text) < 2 or len(text) > 40:
                    continue
                if odds_pattern.match(text) or score_pattern.match(text):
                    continue
                if re.match(r'^[\d: ]+$', text) or re.match(r'^[+-]?\d', text):
                    continue

                is_keyword = any(kw in text for kw in exclude_keywords)
                if is_keyword:
                    continue

                has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
                has_english = any(c.isalpha() for c in text)
                if not has_chinese and not has_english: 
                    continue

                team_candidates.append(elem)

            team_candidates.sort(key=lambda x: x['y'])

            if len(team_candidates) >= 2:
                match['team1'] = team_candidates[0]['text']
                match['team1_y'] = team_candidates[0]['y']

                for candidate in team_candidates[1:]: 
                    if candidate['text'] != match['team1'] and abs(candidate['y'] - match['team1_y']) > 15:
                        match['team2'] = candidate['text']
                        match['team2_y'] = candidate['y']
                        break

                if not match['team2'] and len(team_candidates) >= 2:
                    match['team2'] = team_candidates[1]['text']
                    match['team2_y'] = team_candidates[1]['y']

            elif len(team_candidates) == 1:
                match['team1'] = team_candidates[0]['text']
                match['team1_y'] = team_candidates[0]['y']

            scores = [e for e in match_elements if e['x'] < 80 and score_pattern.match(e['text']) and int(e['text']) <= 20]
            scores.sort(key=lambda x: x['y'])
            if scores:
                match['score1'] = scores[0]['text']
            if len(scores) >= 2:
                match['score2'] = scores[1]['text']

            team1_y = match['team1_y'] if match['team1_y'] else start_y + 40
            team2_y = match['team2_y'] if match['team2_y'] else team1_y + 40

            team1_y_min, team1_y_max = team1_y - 25, team1_y + 25
            team2_y_min, team2_y_max = team2_y - 25, team2_y + 25

            for elem in match_elements:
                if elem['x'] < 400: 
                    continue

                text, x, y = elem['text'], elem['x'], elem['y']

                bet_type = None
                for bt, (x_min, x_max) in LAYOUT_CONFIG.items():
                    if x_min <= x < x_max:
                        bet_type = bt
                        break

                if not bet_type:
                    continue

                if odds_pattern.match(text):
                    odds_obj = {'value': float(text), 'text': text, 'x': x, 'y': y}

                    is_team1_row = (team1_y_min <= y <= team1_y_max)
                    is_team2_row = (team2_y_min <= y <= team2_y_max)

                    if is_team1_row: 
                        match['odds'][bet_type]['home'].append(odds_obj)
                    elif is_team2_row:
                        match['odds'][bet_type]['away'].append(odds_obj)
                    else:
                        dist1 = abs(y - team1_y)
                        dist2 = abs(y - team2_y)
                        if dist1 < dist2:
                            match['odds'][bet_type]['home']. append(odds_obj)
                        else:
                            match['odds'][bet_type]['away']. append(odds_obj)

                    total_odds_count += 1

                elif handicap_pattern.match(text) or text.startswith('大') or text.startswith('小'):
                    match['odds'][bet_type]['handicap'] = text

            if match['team1'] or total_odds_count > 0:
                matches.append(match)

        self.current_matches = matches
        return {'matches': matches, 'totalOdds': total_odds_count, 'statistics': {'total_matches': len(matches), 'total_odds': total_odds_count}}

    def get_all_odds_data(self):
        """综合获取数据"""
        raw_data = self.get_raw_page_data()
        analyzed_data = self.analyze_raw_data(raw_data)
        analyzed_data['_raw'] = raw_data
        return analyzed_data

    def click_odds(self, odds_text, x, y, log_callback):
        """点击水位"""
        try:
            log_callback(f"  点击水位: {odds_text}")
            result = self.driver.execute_script(f"""
                var targetText = '{odds_text}';
                var targetX = {x};
                var targetY = {y};
                var elements = document.querySelectorAll('span, td, div, a');
                var found = null;
                var minDist = 9999;
                for(var i=0; i<elements.length; i++){{
                    var el = elements[i];
                    var text = el.textContent. trim();
                    if(text === targetText && el.offsetWidth > 0){{
                        var rect = el.getBoundingClientRect();
                        var dist = Math.abs(rect.x - targetX) + Math.abs(rect.y - targetY);
                        if(dist < minDist){{ minDist = dist; found = el; }}
                    }}
                }}
                if(found && minDist < 100){{
                    found.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    found.click();
                    return {{success: true}};
                }}
                return {{success:  false}};
            """)
            if result and result.get('success'):
                log_callback("  ✓ 点击成功")
                return True
            return False
        except Exception as e: 
            log_callback(f"  ✗ 点击出错: {e}")
            return False

    def place_bet(self, amount, log_callback):
        """执行下注"""
        try:
            log_callback(f"  执行下注，金额: {amount}")
            time.sleep(1)
            
            result = self.driver.execute_script(f"""
                var inputs = document.querySelectorAll('input');
                for(var i=0; i<inputs.length; i++){{
                    var placeholder = inputs[i].placeholder || '';
                    var id = inputs[i].id || '';
                    if((placeholder. includes('金额') || id.includes('bet') || id.includes('gold')) && inputs[i].offsetWidth > 0){{
                        inputs[i].value = '{amount}';
                        inputs[i].dispatchEvent(new Event('input', {{bubbles: true}}));
                        return {{success: true}};
                    }}
                }}
                return {{success: false}};
            """)
            
            if not result or not result.get('success'):
                log_callback("  ✗ 未找到金额输入框")
                return False
            
            log_callback(f"  ✓ 输入金额: {amount}")
            time.sleep(0.5)
            
            bet_result = self.driver.execute_script("""
                var buttons = document.querySelectorAll('button, div, span');
                for(var i=0; i<buttons.length; i++){
                    var text = buttons[i].textContent. trim();
                    if((text === '下注' || text === '投注' || text === '确认下注') && buttons[i].offsetWidth > 0){
                        buttons[i].click();
                        return {success: true, text: text};
                    }
                }
                return {success:  false};
            """)
            
            if bet_result and bet_result.get('success'):
                log_callback(f"  ✓ 点击下注按钮")
                time.sleep(1)
                return True
            
            log_callback("  ✗ 未找到下注按钮")
            return False
        except Exception as e:
            log_callback(f"  ✗ 下注出错: {e}")
            return False

    def close_bet_panel(self, log_callback=None):
        """关闭下注面板"""
        try:
            self.driver.execute_script("""
                var closes = document.querySelectorAll('[class*="close"], button');
                for(var i=0; i<closes.length; i++){
                    var el = closes[i];
                    if(el.offsetWidth > 0 && el.offsetWidth < 50){
                        el.click();
                        return;
                    }
                }
            """)
            time.sleep(0.5)
        except: 
            pass

    def auto_bet_check(self, log_callback):
        """检查并自动下注"""
        if not self.auto_bet_enabled:
            return False
        
        threshold = self.odds_threshold
        
        for match in self.current_matches:
            team1, team2 = match. get('team1', ''), match.get('team2', '')
            league = match.get('league', '')
            
            for bet_type, type_odds in match. get('odds', {}).items():
                for odds in type_odds.get('home', []) + type_odds.get('away', []):
                    if odds['value'] >= threshold and odds['value'] < 50:
                        bet_key = f"{team1}_{team2}_{bet_type}_{odds['text']}_{datetime.now().strftime('%Y%m%d%H')}"
                        
                        if bet_key in self.bet_history:
                            continue
                        
                        log_callback(f"\n🎯 触发自动下注!  {team1} vs {team2} | {bet_type} | {odds['text']}")
                        
                        if self.click_odds(odds['text'], odds['x'], odds['y'], log_callback):
                            time.sleep(1)
                            if self.place_bet(self.bet_amount, log_callback):
                                self.bet_history. append(bet_key)
                                log_callback(f"  ✓✓ 下注成功!")
                                self.close_bet_panel()
                                return True
                            self.close_bet_panel()
        return False

    def monitor_realtime(self, interval, log_callback, update_callback):
        """实时监控"""
        log_callback(f"\n🚀 开始监控 | 间隔:{interval}秒 | 阈值:{self.odds_threshold}\n")
        
        while self.is_running:
            try: 
                data = self.get_all_odds_data()
                if data:
                    update_callback(data)
                    matches = data.get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    
                    home_count = sum(len(od. get('home', [])) for m in matches for od in m.get('odds', {}).values())
                    away_count = sum(len(od.get('away', [])) for m in matches for od in m.get('odds', {}).values())
                    
                    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {len(matches)}场, {total_odds}水位 (主:{home_count} 客:{away_count})")
                    
                    if self.auto_bet_enabled:
                        self.auto_bet_check(log_callback)
                
                time.sleep(interval)
            except Exception as e:
                log_callback(f"✗ 监控错误: {e}")
                time.sleep(interval)
        
        log_callback("\n监控已停止")

    def stop(self):
        """停止"""
        self.is_running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

# ================== GUI类 ==================
class BettingBotGUI:
    """GUI界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("滚球水位实时监控系统 v4.1")
        self.root.geometry("1850x950")
        self.root.configure(bg='#1a1a2e')
        
        self.bot = BettingBot()
        self.monitor_thread = None
        
        self.create_widgets()
        self.load_config()
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.bot.odds_threshold = config.get('threshold', 1.80)
                    self.bot. bet_amount = config.get('bet_amount', 2)
                    self.threshold_entry.delete(0, tk.END)
                    self.threshold_entry.insert(0, str(self.bot.odds_threshold))
                    self.amount_entry.delete(0, tk.END)
                    self. amount_entry.insert(0, str(self.bot.bet_amount))
        except:
            pass
    
    def save_config(self):
        """保存配置"""
        try:
            config = {
                'threshold': self.bot.odds_threshold,
                'bet_amount': self. bot.bet_amount,
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def create_widgets(self):
        """创建界面"""
        # 标题
        title_frame = tk.Frame(self.root, bg='#1a1a2e')
        title_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(title_frame, text="🎯 滚球水位实时监控系统 v4.1", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 22, 'bold')).pack()
        tk.Label(title_frame, text="修复登录 | 修复球队识别 | 修复主客队水位 | 自动下注",
                bg='#1a1a2e', fg='#888', font=('Microsoft YaHei UI', 10)).pack()
        
        # 主容器
        main_frame = tk.Frame(self.root, bg='#1a1a2e')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # 左侧面板
        left_frame = tk.Frame(main_frame, bg='#16213e', width=340)
        left_frame.pack(side='left', fill='y', padx=(0, 10))
        left_frame.pack_propagate(False)
        
        # 登录区域
        login_frame = tk.LabelFrame(left_frame, text="🔐 登录", bg='#16213e',
                                   fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        login_frame.pack(fill='x', padx=10, pady=(10, 5))
        
        tk.Label(login_frame, text="用户名:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.username_entry = tk.Entry(login_frame, bg='#0f3460', fg='#fff',
                                      font=('Consolas', 10), insertbackground='#fff', relief='flat', width=22)
        self.username_entry.grid(row=0, column=1, pady=3, padx=(5, 0))
        self.username_entry.insert(0, USERNAME)
        
        tk.Label(login_frame, text="密码:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.password_entry = tk.Entry(login_frame, show="*", bg='#0f3460', fg='#fff',
                                      font=('Consolas', 10), insertbackground='#fff', relief='flat', width=22)
        self.password_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.password_entry.insert(0, PASSWORD)
        
        self.login_btn = tk.Button(login_frame, text="登录", bg='#00ff88', fg='#000',
                                  font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                  command=self. login, cursor='hand2', padx=20, pady=3)
        self.login_btn.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        
        # 日志区域
        log_frame = tk.LabelFrame(left_frame, text="📋 日志", bg='#16213e',
                                 fg='#888', font=('Microsoft YaHei UI', 10, 'bold'), padx=5, pady=5)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg='#0f3460', fg='#00ff88',
                                                 font=('Consolas', 9), relief='flat', height=16, wrap='word')
        self.log_text.pack(fill='both', expand=True)
        
        # 下注设置
        self.bet_frame = tk.LabelFrame(left_frame, text="💰 下注设置", bg='#16213e',
                                      fg='#ff9900', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        
        tk.Label(self.bet_frame, text="下注金额:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.amount_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#00ff88',
                                    font=('Consolas', 12, 'bold'), insertbackground='#fff', relief='flat', width=8)
        self.amount_entry.grid(row=0, column=1, pady=3, padx=(5, 0))
        self.amount_entry.insert(0, "2")
        tk.Label(self.bet_frame, text="RMB", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=0, column=2, padx=3)
        
        tk.Label(self.bet_frame, text="刷新间隔:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.interval_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#fff',
                                      font=('Consolas', 12), insertbackground='#fff', relief='flat', width=8)
        self.interval_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.interval_entry.insert(0, "3")
        tk.Label(self.bet_frame, text="秒", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=1, column=2, padx=3)
        
        tk.Label(self.bet_frame, text="水位阈值:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=2, column=0, sticky='w', pady=3)
        self.threshold_entry = tk.Entry(self. bet_frame, bg='#0f3460', fg='#ffaa00',
                                       font=('Consolas', 12, 'bold'), insertbackground='#fff', relief='flat', width=8)
        self.threshold_entry.grid(row=2, column=1, pady=3, padx=(5, 0))
        self.threshold_entry.insert(0, "1.80")
        tk.Label(self.bet_frame, text="≥触发", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=2, column=2, padx=3)
        
        self.auto_bet_var = tk.BooleanVar(value=False)
        self.auto_bet_check = tk.Checkbutton(self.bet_frame, text="⚡ 启用自动下注",
                                            variable=self.auto_bet_var, bg='#16213e', fg='#ff4444',
                                            selectcolor='#0f3460', activebackground='#16213e',
                                            font=('Microsoft YaHei UI', 11, 'bold'), command=self.toggle_auto_bet)
        self.auto_bet_check.grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky='w')
        
        # 控制按��
        self.control_frame = tk.Frame(left_frame, bg='#16213e')
        
        self.start_btn = tk.Button(self.control_frame, text="🚀 开始监控", bg='#0088ff',
                                  fg='#fff', font=('Microsoft YaHei UI', 12, 'bold'), relief='flat',
                                  command=self.start_monitoring, cursor='hand2', pady=10)
        self.start_btn.pack(fill='x', pady=(0, 5))
        
        self.stop_btn = tk.Button(self.control_frame, text="⏹ 停止监控", bg='#ff4444',
                                 fg='#fff', font=('Microsoft YaHei UI', 12, 'bold'), relief='flat',
                                 command=self.stop_monitoring, cursor='hand2', pady=10, state='disabled')
        self.stop_btn.pack(fill='x', pady=(0, 5))
        
        self.refresh_btn = tk.Button(self.control_frame, text="🔄 刷新数据", bg='#666',
                                    fg='#fff', font=('Microsoft YaHei UI', 10), relief='flat',
                                    command=self.refresh_data, cursor='hand2', pady=6)
        self.refresh_btn.pack(fill='x', pady=(0, 5))
        
        self.diagnose_btn = tk.Button(self.control_frame, text="🔬 深度诊断", bg='#9933ff',
                                     fg='#fff', font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                     command=self. diagnose_page, cursor='hand2', pady=6)
        self.diagnose_btn.pack(fill='x')
        
        # 右侧数据区域
        self.right_frame = tk.Frame(main_frame, bg='#16213e')
        self.right_frame.pack(side='right', fill='both', expand=True)
        
        # 标题栏
        header_frame = tk.Frame(self.right_frame, bg='#16213e')
        header_frame.pack(fill='x', pady=(0, 5))
        
        tk.Label(header_frame, text="📊 实时水位数据", bg='#16213e',
                font=('Microsoft YaHei UI', 14, 'bold'), fg='#00ff88').pack(side='left')
        
        self.update_label = tk.Label(header_frame, text="", bg='#16213e',
                                    font=('Microsoft YaHei UI', 10), fg='#ffaa00')
        self.update_label.pack(side='right', padx=10)
        
        # 提示
        self.hint_label = tk.Label(self.right_frame,
                                  text="请先登录\n\n登录后将显示所有滚球比赛的水位数据\n\n点击「深度诊断」可分析页面结构",
                                  bg='#16213e', fg='#888', font=('Microsoft YaHei UI', 12), justify='center')
        self.hint_label.pack(pady=100)
        
        self.odds_canvas = None
        self.odds_inner_frame = None
        
        # 状态栏
        status_frame = tk.Frame(self.root, bg='#0f3460', height=30)
        status_frame.pack(side='bottom', fill='x')
        
        self.status_label = tk.Label(status_frame, text="状态: 未登录", bg='#0f3460',
                                    fg='#888', font=('Microsoft YaHei UI', 10), anchor='w', padx=20)
        self.status_label.pack(side='left', fill='y')
        
        self.time_label = tk.Label(status_frame, text="", bg='#0f3460',
                                  fg='#00ff88', font=('Microsoft YaHei UI', 10), anchor='e', padx=20)
        self.time_label.pack(side='right', fill='y')
    
    def create_odds_display_area(self, parent):
        """创建水位显示区域"""
        if self.hint_label: 
            self.hint_label. pack_forget()
        
        if self.odds_canvas:
            self.odds_canvas. master.destroy()
        
        canvas_frame = tk.Frame(parent, bg='#16213e')
        canvas_frame.pack(fill='both', expand=True)
        
        self.odds_canvas = tk.Canvas(canvas_frame, bg='#0f3460', highlightthickness=0)
        scrollbar_y = tk.Scrollbar(canvas_frame, orient='vertical', command=self.odds_canvas.yview)
        scrollbar_x = tk.Scrollbar(canvas_frame, orient='horizontal', command=self.odds_canvas.xview)
        
        self. odds_inner_frame = tk.Frame(self.odds_canvas, bg='#0f3460')
        
        self.odds_canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        scrollbar_y.pack(side='right', fill='y')
        scrollbar_x.pack(side='bottom', fill='x')
        self.odds_canvas.pack(side='left', fill='both', expand=True)
        
        self.canvas_window = self.odds_canvas.create_window((0, 0), window=self.odds_inner_frame, anchor='nw')
        
        self.odds_inner_frame.bind('<Configure>', lambda e: self.odds_canvas. configure(scrollregion=self. odds_canvas.bbox('all')))
        self.odds_canvas.bind('<Configure>', lambda e: self.odds_canvas.itemconfig(self.canvas_window, width=e.width))
        self.odds_canvas.bind_all('<MouseWheel>', lambda e: self.odds_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))
    
    def update_odds_display(self, data):
        """更新水位显示"""
        def update():
            try:
                if not self.odds_inner_frame:
                    self.create_odds_display_area(self.right_frame)
                
                matches = data.get('matches', [])
                total_odds = data.get('totalOdds', 0)
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                self.time_label.config(text=f"最后更新: {timestamp}")
                self.update_label.config(text=f"🔄 {timestamp}", fg='#00ff88')
                
                # 清除旧内容
                for widget in self. odds_inner_frame.winfo_children():
                    widget. destroy()
                
                if not matches:
                    tk.Label(self.odds_inner_frame, text="暂无比赛数据，请点击「深度诊断」查看详情",
                            bg='#0f3460', fg='#888', font=('Microsoft YaHei UI', 11)).pack(pady=20)
                    return
                
                # 统计
                home_total = sum(len(od. get('home', [])) for m in matches for od in m.get('odds', {}).values())
                away_total = sum(len(od.get('away', [])) for m in matches for od in m.get('odds', {}).values())
                
                tk.Label(self.odds_inner_frame,
                        text=f"共 {len(matches)} 场比赛，{total_odds} 个水位 (主队:{home_total} 客队:{away_total})  |  阈值:  {self.bot. odds_threshold}",
                        bg='#0f3460', fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', padx=10, pady=5)
                
                current_league = ''
                threshold = self.bot.odds_threshold
                display_bet_types = BET_TYPES_ORDER[: 8]
                
                for match in matches:
                    league = match.get('league', '未知联赛')
                    team1 = match.get('team1', '主队')
                    team2 = match.get('team2', '客队')
                    score1 = match.get('score1', '0')
                    score2 = match.get('score2', '0')
                    match_time = match.get('time', '')
                    odds = match.get('odds', {})
                    
                    # 联赛标题
                    if league and league != current_league:
                        league_frame = tk.Frame(self.odds_inner_frame, bg='#2d2d44')
                        league_frame.pack(fill='x', pady=(15, 5), padx=5)
                        tk.Label(league_frame, text=f"🏆 {league}", bg='#2d2d44', fg='#ffaa00',
                                font=('Microsoft YaHei UI', 12, 'bold'), pady=5).pack(anchor='w', padx=10)
                        current_league = league
                    
                    # 比赛容器
                    match_frame = tk.Frame(self.odds_inner_frame, bg='#1e1e32', bd=1, relief='solid')
                    match_frame. pack(fill='x', padx=5, pady=3)
                    
                    # 表头行
                    info_frame = tk.Frame(match_frame, bg='#1e1e32')
                    info_frame.pack(fill='x', pady=(5, 2), padx=5)
                    
                    tk.Label(info_frame, text=f"⏱ {match_time}", bg='#1e1e32', fg='#888',
                            font=('Microsoft YaHei UI', 9), width=18, anchor='w').pack(side='left')
                    
                    for bt in display_bet_types: 
                        tk.Label(info_frame, text=bt, bg='#1e1e32', fg='#aaa',
                                font=('Microsoft YaHei UI', 8), width=10, anchor='center').pack(side='left', padx=1)
                    
                    # 主队行
                    team1_frame = tk.Frame(match_frame, bg='#1e1e32')
                    team1_frame.pack(fill='x', pady=2, padx=5)
                    
                    score_color = '#ff4444' if score1 and score1. isdigit() and int(score1) > 0 else '#fff'
                    tk.Label(team1_frame, text=score1 or '0', bg='#1e1e32', fg=score_color,
                            font=('Microsoft YaHei UI', 11, 'bold'), width=3).pack(side='left')
                    tk.Label(team1_frame, text=team1[: 14], bg='#1e1e32', fg='#fff',
                            font=('Microsoft YaHei UI', 10), width=14, anchor='w').pack(side='left')
                    
                    for bt in display_bet_types: 
                        cell_frame = tk.Frame(team1_frame, bg='#1e1e32', width=80)
                        cell_frame. pack(side='left', padx=1)
                        cell_frame.pack_propagate(False)
                        
                        type_odds = odds.get(bt, {})
                        home_odds = type_odds.get('home', [])
                        handicap = type_odds.get('handicap', '')
                        
                        cell_inner = tk.Frame(cell_frame, bg='#1e1e32')
                        cell_inner.pack(expand=True)
                        
                        if handicap:
                            tk.Label(cell_inner, text=handicap, bg='#1e1e32', fg='#666',
                                    font=('Consolas', 7)).pack()
                        
                        if home_odds:
                            val = home_odds[0]['value']
                            text = home_odds[0]['text']
                            color = '#ff4444' if val >= threshold else '#00ff88'
                            tk.Label(cell_inner, text=text, bg='#1e1e32', fg=color,
                                    font=('Consolas', 10, 'bold')).pack()
                        else:
                            tk.Label(cell_inner, text="-", bg='#1e1e32', fg='#444',
                                    font=('Consolas', 10)).pack()
                    
                    # 客队行
                    team2_frame = tk.Frame(match_frame, bg='#1e1e32')
                    team2_frame.pack(fill='x', pady=(0, 5), padx=5)
                    
                    score_color = '#ff4444' if score2 and score2.isdigit() and int(score2) > 0 else '#fff'
                    tk.Label(team2_frame, text=score2 or '0', bg='#1e1e32', fg=score_color,
                            font=('Microsoft YaHei UI', 11, 'bold'), width=3).pack(side='left')
                    tk.Label(team2_frame, text=team2[:14], bg='#1e1e32', fg='#fff',
                            font=('Microsoft YaHei UI', 10), width=14, anchor='w').pack(side='left')
                    
                    for bt in display_bet_types: 
                        cell_frame = tk.Frame(team2_frame, bg='#1e1e32', width=80)
                        cell_frame. pack(side='left', padx=1)
                        cell_frame.pack_propagate(False)
                        
                        type_odds = odds.get(bt, {})
                        away_odds = type_odds.get('away', [])
                        
                        cell_inner = tk. Frame(cell_frame, bg='#1e1e32')
                        cell_inner.pack(expand=True)
                        
                        tk.Label(cell_inner, text="", bg='#1e1e32', font=('Consolas', 7)).pack()
                        
                        if away_odds:
                            val = away_odds[0]['value']
                            text = away_odds[0]['text']
                            color = '#ff4444' if val >= threshold else '#ffaa00'
                            tk. Label(cell_inner, text=text, bg='#1e1e32', fg=color,
                                    font=('Consolas', 10, 'bold')).pack()
                        else:
                            tk.Label(cell_inner, text="-", bg='#1e1e32', fg='#444',
                                    font=('Consolas', 10)).pack()
                
                self.odds_inner_frame.update_idletasks()
                self. odds_canvas.configure(scrollregion=self.odds_canvas.bbox('all'))
                
            except Exception as e: 
                print(f"更新显示出错: {e}")
                import traceback
                traceback.print_exc()
        
        self.root.after(0, update)
    
    def log(self, message):
        """写日志"""
        def update_log():
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_text.insert('end', f"[{timestamp}] {message}\n")
            self.log_text.see('end')
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 500:
                self.log_text.delete('1.0', '200.0')
        self.root.after(0, update_log)
    
    def toggle_auto_bet(self):
        """切换自动下注"""
        if self.auto_bet_var.get():
            result = messagebox.askyesno("确认启用自动下注",
                f"确定启用自动下注吗？\n\n水位 ≥ {self.threshold_entry.get()} 时将自动下注\n下注金额:  {self.amount_entry.get()} RMB\n\n请确保账户余额充足！")
            if result:
                self.bot.auto_bet_enabled = True
                self.bot.odds_threshold = float(self.threshold_entry.get())
                self.bot.bet_amount = float(self.amount_entry.get())
                self.save_config()
                self.log("⚡ 自动下注已启用!")
            else:
                self.auto_bet_var.set(False)
        else:
            self.bot.auto_bet_enabled = False
            self.log("自动下注已关闭")
    
    def login(self):
        """登录"""
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showerror("错误", "请输入用户名和密码")
            return
        
        self.login_btn.config(state='disabled', text="登录中...")
        self.status_label.config(text="状态: 登录中.. .", fg='#ffaa00')
        
        def login_thread():
            try:
                self.bot.setup_driver(headless=False)
                success = self.bot.login(username, password, self.log)
                
                def update_ui():
                    if success: 
                        self.status_label. config(text="状态: 已登录", fg='#00ff88')
                        self.login_btn.config(text="✓ 已登录", state='disabled')
                        self.bet_frame.pack(fill='x', padx=10, pady=5)
                        self.control_frame.pack(fill='x', padx=10, pady=10)
                        self.create_odds_display_area(self.right_frame)
                        self.refresh_data()
                    else:
                        self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                        self. login_btn.config(state='normal', text="登录")
                
                self.root.after(0, update_ui)
            except Exception as e:
                self.log(f"登录异常: {e}")
                def update_ui():
                    self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                    self.login_btn.config(state='normal', text="登录")
                self.root.after(0, update_ui)
        
        threading.Thread(target=login_thread, daemon=True).start()
    
    def start_monitoring(self):
        """开始监控"""
        try:
            interval = float(self.interval_entry.get())
            amount = float(self.amount_entry.get())
            threshold = float(self.threshold_entry.get())
        except ValueError:
            messagebox. showerror("错误", "请输入有效数字")
            return
        
        if interval < 1:
            messagebox.showwarning("警告", "刷新间隔不能小于1秒")
            return
        
        self. bot.bet_amount = amount
        self. bot.odds_threshold = threshold
        self.bot.auto_bet_enabled = self.auto_bet_var.get()
        self.bot.is_running = True
        self.save_config()
        
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="状态:  监控中.. .", fg='#00ff88')
        
        self.log(f"🚀 开始监控 | 间隔:{interval}秒 | 阈值:{threshold} | 金额:{amount}")
        
        self.monitor_thread = threading.Thread(
            target=self.bot.monitor_realtime,
            args=(interval, self.log, self.update_odds_display),
            daemon=True
        )
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控"""
        self.bot. is_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="状态:  已停止", fg='#ffaa00')
        self.update_label.config(text="⏹ 已停止", fg='#ffaa00')
        self.log("监控已停止")
    
    def refresh_data(self):
        """手动刷新数据"""
        def refresh_thread():
            self.log("正在刷新数据...")
            
            def update_status():
                self.update_label.config(text="🔄 刷新中.. .", fg='#ffaa00')
            self.root.after(0, update_status)
            
            try:
                self.bot.wait_for_matches_to_load(self.log)
                data = self.bot.get_all_odds_data()
                
                if data:
                    matches = data.get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    
                    home_count = sum(len(od.get('home', [])) for m in matches for od in m. get('odds', {}).values())
                    away_count = sum(len(od.get('away', [])) for m in matches for od in m.get('odds', {}).values())
                    
                    self.update_odds_display(data)
                    self.log(f"✓ 获取 {len(matches)} 场比赛, {total_odds} 水位 (主:{home_count} 客:{away_count})")
                    
                    for match in matches[: 3]: 
                        self.log(f"  {match. get('score1', '0')} {match.get('team1', '? ')} vs {match.get('team2', '?')} {match.get('score2', '0')}")
                else:
                    self.log("❌ 未获取到数据")
            except Exception as e:
                self.log(f"刷新失败: {e}")
                import traceback
                self.log(traceback.format_exc())
        
        threading. Thread(target=refresh_thread, daemon=True).start()
    
    def diagnose_page(self):
        """深度诊断"""
        if not self.bot.driver:
            messagebox.showerror("错误", "请先登录")
            return
        
        def diagnose_thread():
            self.log("\n" + "="*50)
            self.log("🔬 开始深度诊断...")
            self.log("="*50)
            
            try:
                self.bot.wait_for_matches_to_load(self.log)
                
                raw_data = self.bot.get_raw_page_data()
                elements = raw_data.get('elements', [])
                self.log(f"\n📊 获取到 {len(elements)} 个元素")
                
                # 分析盘口标题
                self.log("\n📍 盘口标题X坐标:")
                bet_keywords = ['让球', '大/小', '独赢', '下个进球', '双方球队进球', '单/双']
                bet_coords = {}
                for elem in elements:
                    for kw in bet_keywords:
                        if kw in elem['text'] and len(elem['text']) < 20:
                            if kw not in bet_coords: 
                                bet_coords[kw] = []
                            bet_coords[kw].append(elem['x'])
                
                for kw in bet_keywords:
                    if kw in bet_coords: 
                        coords = bet_coords[kw]
                        self.log(f"  {kw}: X={int(sum(coords)/len(coords))} (范围:{min(coords)}-{max(coords)})")
                
                # 分析球队名
                self.log("\n🏃 可能的球队名:")
                teams = [e for e in elements if e['x'] < 280 and 2 <= len(e['text']) <= 35
                        and not re.match(r'^[\d:. +-/]+$', e['text'])
                        and not any(kw in e['text'] for kw in ['让球', '大小', '独赢', '进球', '半场'])]
                for i, t in enumerate(teams[: 15]):
                    self.log(f"  [{i+1}] X={t['x']: 4d} Y={t['y']:4d}:  {t['text']}")
                
                # 分析水位
                self.log("\n💰 水位X坐标分布:")
                odds_pattern = re.compile(r'^\d{1,2}\.\d{1,2}$')
                odds_elems = [e for e in elements if odds_pattern.match(e['text'])]
                
                x_dist = {}
                for e in odds_elems:
                    x_range = (e['x'] // 80) * 80
                    x_dist[x_range] = x_dist.get(x_range, 0) + 1
                
                for x_range in sorted(x_dist.keys()):
                    self.log(f"  X={x_range: 4d}-{x_range+79}:  {x_dist[x_range]: 3d}个")
                
                # 运行分析
                analyzed = self.bot.analyze_raw_data(raw_data)
                matches = analyzed.get('matches', [])
                
                self.log(f"\n✅ 分析结果: {len(matches)} 场比赛")
                for i, m in enumerate(matches[: 5]):
                    home_c = sum(len(od.get('home', [])) for od in m.get('odds', {}).values())
                    away_c = sum(len(od.get('away', [])) for od in m.get('odds', {}).values())
                    self.log(f"  [{i+1}] {m.get('team1', '?')} vs {m.get('team2', '?')} | 主:{home_c} 客:{away_c}")
                
                self.update_odds_display(analyzed)
                
                self.log("\n" + "="*50)
                self.log("✅ 诊断完成!")
                self.log("="*50)
                
            except Exception as e: 
                self.log(f"\n❌ 诊断出错: {e}")
                import traceback
                self.log(traceback.format_exc())
        
        threading.Thread(target=diagnose_thread, daemon=True).start()
    
    def on_closing(self):
        """关闭窗口"""
        if messagebox.askokcancel("退出", "确定退出程序？"):
            self.save_config()
            self.bot.stop()
            self.root.destroy()


# ================== 主程序入口 ==================
if __name__ == "__main__":
    root = tk. Tk()
    app = BettingBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
