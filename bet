from selenium import webdriver
from selenium.webdriver.common.by import By
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

# ================== 配置 ==================
URL = "https://mos055.com/"
USERNAME = "LJJ123123"
PASSWORD = "zz66688899"
COOKIES_FILE = "mos055_cookies.pkl"

# ================== BettingBot 类 ==================
class BettingBot: 
    def __init__(self):
        self.driver = None
        self.is_running = False
        self. is_logged_in = False
        self.wait = None
        self.auto_bet_enabled = False
        self.bet_amount = 2
        self.bet_history = []
        self.threshold_settings = {}
        self.current_matches = []
        self.font_map = {}

    def setup_driver(self, headless=False):
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
        self.wait = WebDriverWait(self. driver, 60)

        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            '''
        })

    def handle_password_popup(self, log_callback):
        log_callback("检测并处理简易密码弹窗...")

        for attempt in range(15):
            try:
                popup_visible = self.driver.execute_script("""
                    var popup = document.getElementById('c_alert_modify');
                    if (popup) {
                        var style = window.getComputedStyle(popup);
                        return popup.offsetWidth > 0 && popup.offsetHeight > 0 &&
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
                            elem.offsetWidth > 0 && elem.offsetHeight > 0) {
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
        """等待比赛数据加载并滚动触发"""
        log_callback("\n⏳ 等待比赛数据加载...")

        for attempt in range(10):
            time.sleep(2)

            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)

            has_matches = self.driver.execute_script("""
                var elements = document.querySelectorAll('*');
                var foundMatch = false;

                for (var i = 0; i < elements.length; i++) {
                    var text = elements[i].textContent || '';
                    if (/(Esports|vs|FIFA|Real Madrid|Manchester|半场|上半场|下半场|让球|大小)/i.test(text) &&
                        text.length > 3 && text.length < 200) {
                        var rect = elements[i].getBoundingClientRect();
                        if (rect.y > 100 && rect.y < 3000 && rect.width > 50) {
                            foundMatch = true;
                            break;
                        }
                    }
                }

                return foundMatch;
            """)

            if has_matches:
                log_callback(f"✓ 检测到比赛数据 (尝试 {attempt + 1}/10)")
                time.sleep(2)
                return True

            log_callback(f"  尝试 {attempt + 1}/10 - 未检测到数据，继续等待...")

        log_callback("⚠️ 等待超时，但继续尝试获取数据")
        return False

    def decode_tahoma2_font(self, log_callback):
        """分析 TAHOMA2 自定义字体"""
        log_callback("\n🔤 分析 TAHOMA 字体...")

        font_map = self.driver.execute_script("""
            function decodeTahoma2() {
                var samples = [];
                var allElements = document.querySelectorAll('*');

                allElements.forEach(function(elem) {
                    var style = window.getComputedStyle(elem);
                    var fontFamily = style.fontFamily || '';

                    if (fontFamily.toUpperCase().includes('TAHOMA')) {
                        var rect = elem.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && rect.y > 50 && rect.y < 2000) {
                            var text = elem.textContent || '';

                            samples.push({
                                text: text. substring(0, 50),
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math. round(rect.height),
                                fontFamily: fontFamily
                            });
                        }
                    }
                });

                samples.sort(function(a, b) { return a.y - b.y; });

                return {
                    samples: samples. slice(0, 50),
                    count: samples.length
                };
            }

            return decodeTahoma2();
        """)

        log_callback(f"  找到 {font_map.get('count', 0)} 个使用 TAHOMA 字体的元素")

        return font_map

    def find_match_container(self, log_callback):
        """定位比赛列表容器"""
        log_callback("\n🎯 定位比赛列表区域...")

        container_info = self.driver.execute_script("""
            function findMatchContainer() {
                var result = {
                    byClassName: [],
                    byContent: []
                };

                var classPatterns = ['match', 'event', 'game', 'odds', 'bet', 'league'];
                classPatterns.forEach(function(pattern) {
                    var elems = document.querySelectorAll('[class*="' + pattern + '"]');
                    elems. forEach(function(elem) {
                        var rect = elem.getBoundingClientRect();
                        if (rect. height > 100 && rect.width > 400 && rect.y > 50 && rect.y < 1500) {
                            result. byClassName.push({
                                pattern: pattern,
                                className: elem.className. substring(0, 80),
                                y: Math.round(rect.y),
                                height: Math.round(rect.height)
                            });
                        }
                    });
                });

                return result;
            }

            return findMatchContainer();
        """)

        log_callback(f"  通过类名找到:  {len(container_info.get('byClassName', []))} 个")

        return container_info

    def get_raw_elements(self, log_callback):
        """获取原始元素用于诊断"""
        log_callback("\n📊 获取原始元素...")

        raw_data = self.driver.execute_script("""
            function getRawElements() {
                var elements = [];
                var allElems = document.querySelectorAll('*');

                allElems.forEach(function(elem) {
                    var rect = elem. getBoundingClientRect();
                    if (rect.width > 10 && rect.width < 200 &&
                        rect.height > 8 && rect.height < 60 &&
                        rect.y > 150 && rect.y < 2000 &&
                        rect.x > 30) {

                        var text = elem.textContent || '';
                        if (text.trim() && text.length < 50) {
                            elements.push({
                                text: text. trim(),
                                x: Math. round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                tag: elem.tagName
                            });
                        }
                    }
                });

                elements.sort(function(a, b) {
                    if (Math.abs(a.y - b.y) < 12) {
                        return a. x - b.x;
                    }
                    return a. y - b.y;
                });

                return elements;
            }
            return getRawElements();
        """)

        log_callback(f"  找到 {len(raw_data)} 个可能的元素")

        current_y = -1
        row_num = 0
        for elem in raw_data[: 80]: 
            if abs(elem['y'] - current_y) > 12:
                row_num += 1
                current_y = elem['y']
                log_callback(f"\n  行 {row_num} (Y={elem['y']}):")

            log_callback(f"    X={elem['x']: 4d} [{elem['text'][:25]}]")

        return raw_data

    def login(self, username, password, log_callback):
        try:
            log_callback("正在访问登录页面...")
            self.driver.get(URL)
            time.sleep(8)

            username_field = self.wait.until(EC.element_to_be_clickable((By.ID, "usr")))
            log_callback("✓ 找到用户名输入框")
            self.driver.execute_script("arguments[0].value = arguments[1];", username_field, username)
            log_callback(f"✓ 已输入用户名: {username}")

            password_field = self.wait.until(EC.element_to_be_clickable((By.ID, "pwd")))
            self.driver.execute_script("arguments[0].value = arguments[1];", password_field, password)
            log_callback("✓ 已输入密码")

            login_button = self.wait.until(EC.element_to_be_clickable((By.ID, "btn_login")))
            self.driver.execute_script("arguments[0].click();", login_button)
            log_callback("✓ 已点击登录按钮")

            log_callback("\n等待登录响应...")
            time.sleep(10)

            self.handle_password_popup(log_callback)
            time.sleep(3)

            log_callback("\n等待主页面加载...")
            for i in range(12):
                time.sleep(5)
                elapsed = (i + 1) * 5
                log_callback(f"  已等待 {elapsed} 秒...")

                if elapsed % 10 == 0:
                    try:
                        found = self.driver.execute_script("""
                            var elements = document.querySelectorAll('*');
                            for (var elem of elements) {
                                var text = (elem.textContent || '').trim();
                                if (text === '滚球' && elem.offsetWidth > 0 && elem. offsetHeight > 0) {
                                    return true;
                                }
                            }
                            return false;
                        """)
                        if found:
                            log_callback(f"✓ 页面已加载完成")
                            break
                    except:
                        pass

            log_callback(f"\n当前URL: {self.driver.current_url}")

            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "wb") as f:
                pickle.dump(cookies, f)
            log_callback(f"✓ Cookies 已保存")

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

            if click_result.get('success'):
                log_callback(f"✓ 已点击滚球")

            log_callback("等待滚球页面加载...")
            time.sleep(10)

            self.wait_for_matches_to_load(log_callback)

            self.is_logged_in = True
            log_callback("\n✓ 登录流程完成！")

            return True

        except Exception as e:
            log_callback(f"\n✗ 登录失败: {str(e)}")
            return False

    def get_all_odds_data(self):
        """获取页面上所有水位数据 - 修复版：不按盘口类型分类，直接收集所有水位"""
        try:
            # 多次滚动确保数据加载
            self.driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(0.5)
            self.driver.execute_script("window. scrollTo(0, 400);")
            time.sleep(0.8)

            data = self.driver.execute_script("""
                function getAllOddsData() {
                    var matches = [];
                    var allTextData = [];
                    var debugInfo = {
                        totalScanned: 0,
                        tahoma2Elements: 0,
                        fromDataAttr: 0,
                        fromPseudo: 0,
                        fromText: 0,
                        privateUnicode: 0,
                        teamNamesFound: 0,
                        oddsFound: 0,
                        matchesDetected: 0
                    };

                    // ========== 获取文本的多种方法 ==========
                    function getFromDataAttributes(elem) {
                        var attrs = ['data-value', 'data-odds', 'data-num', 'data-price',
                                    'data-text', 'data-content', 'data-v', 'data-o', 'data-bet'];

                        for (var i = 0; i < attrs.length; i++) {
                            var val = elem.getAttribute(attrs[i]);
                            if (val && /[\\d\\.]/.test(val)) {
                                debugInfo. fromDataAttr++;
                                return val;
                            }
                        }

                        for (var j = 0; j < elem. attributes.length; j++) {
                            var attr = elem.attributes[j];
                            if (attr.name. startsWith('data-') && /^[\\d\\.\\-\\+\\/]+$/.test(attr.value)) {
                                debugInfo. fromDataAttr++;
                                return attr.value;
                            }
                        }

                        return null;
                    }

                    function getFromPseudoElements(elem) {
                        try {
                            var before = window.getComputedStyle(elem, '::before').content;
                            var after = window.getComputedStyle(elem, '::after').content;

                            var result = '';

                            if (before && before !== 'none' && before !== 'normal') {
                                result += before. replace(/['"]/g, '');
                            }

                            if (after && after !== 'none' && after !== 'normal') {
                                result += after.replace(/['"]/g, '');
                            }

                            if (result && /\\d/. test(result)) {
                                debugInfo.fromPseudo++;
                                return result. trim();
                            }
                        } catch(e) {}

                        return null;
                    }

                    function tryDecodePrivateUnicode(text) {
                        if (!text) return null;

                        var decoded = '';
                        var hasPrivate = false;

                        for (var i = 0; i < text.length; i++) {
                            var code = text.charCodeAt(i);

                            if (code >= 0xE000 && code <= 0xF8FF) {
                                hasPrivate = true;
                                debugInfo.privateUnicode++;

                                var mapped = code - 0xE000;
                                if (mapped >= 0 && mapped <= 9) {
                                    decoded += mapped. toString();
                                } else if (code === 0xE02E || code === 0xE02D) {
                                    decoded += '. ';
                                } else {
                                    decoded += '? ';
                                }
                            } else {
                                decoded += text[i];
                            }
                        }

                        if (hasPrivate) {
                            return decoded;
                        }

                        return null;
                    }

                    function getFromAriaOrTitle(elem) {
                        var ariaLabel = elem.getAttribute('aria-label');
                        var ariaValue = elem.getAttribute('aria-valuenow');
                        var title = elem.getAttribute('title');

                        var value = ariaLabel || ariaValue || title;
                        if (value && /\\d/.test(value)) {
                            return value;
                        }
                        return null;
                    }

                    function getElementText(elem) {
                        var methods = [
                            function() { return getFromDataAttributes(elem); },
                            function() { return getFromAriaOrTitle(elem); },
                            function() { return getFromPseudoElements(elem); },
                            function() {
                                var t = elem.textContent || '';
                                var decoded = tryDecodePrivateUnicode(t);
                                if (decoded) return decoded;
                                return null;
                            },
                            function() {
                                var t = elem. innerText || elem.textContent || '';
                                t = t.split('\\n')[0]. trim();
                                if (t && t.length < 60) {
                                    debugInfo.fromText++;
                                    return t;
                                }
                                return null;
                            }
                        ];

                        for (var i = 0; i < methods.length; i++) {
                            try {
                                var result = methods[i]();
                                if (result && result. trim()) {
                                    return result.trim();
                                }
                            } catch(e) {}
                        }

                        return '';
                    }

                    // ========== 遍历页面元素收集所有文本 ==========
                    var allElements = document.querySelectorAll('*');

                    allElements.forEach(function(elem) {
                        debugInfo.totalScanned++;

                        try {
                            var rect = elem.getBoundingClientRect();

                            if (rect.width <= 0 || rect.height <= 0) return;
                            if (rect.y < 50 || rect.y > 3000) return;

                            var style = window.getComputedStyle(elem);
                            var fontFamily = style.fontFamily || '';
                            if (fontFamily.toUpperCase().includes('TAHOMA')) {
                                debugInfo.tahoma2Elements++;
                            }

                            var text = getElementText(elem);

                            if (text && text. length > 0 && text.length < 80) {
                                allTextData.push({
                                    text: text,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height),
                                    tagName: elem.tagName,
                                    className: elem.className || ''
                                });
                            }
                        } catch(e) {}
                    });

                    // 去重
                    var seen = new Set();
                    var uniqueData = [];
                    allTextData.forEach(function(item) {
                        var key = item.text + '_' + item.x + '_' + item.y;
                        if (!seen.has(key)) {
                            seen.add(key);
                            uniqueData.push(item);
                        }
                    });
                    allTextData = uniqueData;

                    // ========== 定义正则表达式 ==========
                    var oddsPattern = /^\\d{1,2}\\.\\d{1,3}$/;
                    var timePattern = /(上半场|下半场|中场|半场|第[一二三四1-4]节)\\s*\\d+/;
                    var leaguePattern = /(杯|联赛|U23|U20|U21|超级|甲级|乙级|亚洲|NBA|CBA|足球|篮球|Esports|电竞|FIFA|GT|模拟|女)/i;

                    // ========== 找到所有比赛的起始位置 ==========
                    var matchStarts = [];
                    allTextData.forEach(function(item) {
                        if (timePattern.test(item.text) && item.x < 250) {
                            matchStarts.push({
                                time: item.text,
                                y: item.y,
                                x: item.x
                            });
                        }
                    });

                    // 按Y坐标排序
                    matchStarts.sort(function(a, b) { return a.y - b.y; });
                    debugInfo.matchesDetected = matchStarts. length;

                    // 查找联赛名称
                    function findLeagueForY(y) {
                        var league = '';
                        allTextData.forEach(function(item) {
                            if (leaguePattern.test(item. text) && item.text.length > 3 && 
                                item.text.length < 80 && item.y < y) {
                                league = item. text;
                            }
                        });
                        return league;
                    }

                    // ========== 对每场比赛提取数据 ==========
                    matchStarts.forEach(function(matchStart, idx) {
                        var matchId = idx + 1;
                        
                        // 比赛Y坐标范围
                        var startY = matchStart.y;
                        var endY = matchStarts[idx + 1] ? matchStarts[idx + 1].y - 10 : startY + 250;

                        var match = {
                            id: matchId,
                            league: findLeagueForY(startY),
                            time:  matchStart.time,
                            team1: '',
                            team1Score: '',
                            team2: '',
                            team2Score:  '',
                            team1Odds: [],
                            team2Odds:  [],
                            allOdds: []  // 🆕 收集所有水位
                        };

                        // 在Y范围内找球队名
                        var teamsInRange = allTextData.filter(function(item) {
                            return item.y > startY && item.y < endY &&
                                   item.x < 280 &&
                                   item.text.length >= 2 && item.text.length <= 50 &&
                                   !oddsPattern.test(item.text) &&
                                   !/^\\d+$/.test(item.text) &&
                                   !/^[+-]? \\d+(\\.\\d)?/. test(item.text) &&
                                   ! /(让球|大小|独赢|进球|单双|半场|上半场|下半场|主|客|大|小|vs|确认|其他|热门|今日|早盘|赛事)/.test(item.text) &&
                                   (/[\\u4e00-\\u9fa5]{2,}/.test(item. text) || /[A-Za-z]{3,}/.test(item.text) || /\\([^)]+\\)/.test(item.text));
                        });

                        // 按Y排序
                        teamsInRange.sort(function(a, b) { return a.y - b.y; });

                        // 取前2个作为主队和客队
                        if (teamsInRange[0]) {
                            match.team1 = teamsInRange[0].text;
                            debugInfo.teamNamesFound++;
                        }
                        if (teamsInRange[1]) {
                            match.team2 = teamsInRange[1].text;
                            debugInfo.teamNamesFound++;
                        }

                        // 找比分
                        var scoresInRange = allTextData. filter(function(item) {
                            return item.y > startY && item.y < endY &&
                                   item.x < 150 && item.x > 30 &&
                                   /^\\d{1,3}$/.test(item.text) &&
                                   parseInt(item.text) <= 50;
                        });
                        scoresInRange.sort(function(a, b) { return a.y - b.y; });
                        if (scoresInRange[0]) match.team1Score = scoresInRange[0].text;
                        if (scoresInRange[1]) match.team2Score = scoresInRange[1].text;

                        // 确定主队和客队的Y坐标
                        var team1Y = teamsInRange[0] ? teamsInRange[0]. y : startY + 40;
                        var team2Y = teamsInRange[1] ? teamsInRange[1]. y : team1Y + 20;
                        var rowHeight = Math.abs(team2Y - team1Y);
                        if (rowHeight < 10) rowHeight = 20;

                        // 🆕 收集该比赛范围内所有水位（X > 300的区域）
                        var allOddsInMatch = allTextData.filter(function(item) {
                            return item.y > startY && item.y < endY &&
                                   item.x > 300 &&
                                   oddsPattern.test(item.text);
                        });

                        // 按位置排序
                        allOddsInMatch.sort(function(a, b) {
                            if (Math.abs(a.y - b.y) < 10) {
                                return a.x - b.x;
                            }
                            return a.y - b.y;
                        });

                        // 🆕 根据Y坐标判断主队还是客队
                        allOddsInMatch.forEach(function(o, index) {
                            var distToTeam1 = Math.abs(o.y - team1Y);
                            var distToTeam2 = Math.abs(o.y - team2Y);

                            var oddsObj = {
                                betType: '水位' + (index + 1),  // 简单编号
                                value: parseFloat(o.text),
                                text: o.text,
                                handicap: '',
                                x: o.x,
                                y: o.y
                            };

                            // 根据距离判断归属
                            if (distToTeam1 < distToTeam2) {
                                match.team1Odds.push(oddsObj);
                            } else {
                                match.team2Odds.push(oddsObj);
                            }

                            match.allOdds.push(oddsObj);
                            debugInfo.oddsFound++;
                        });

                        // 只添加有效的比赛
                        if (match.team1 || match.allOdds.length > 0) {
                            matches.push(match);
                        }
                    });

                    // 统计
                    var totalOdds = 0;
                    matches.forEach(function(m) {
                        totalOdds += (m.team1Odds ?  m.team1Odds.length : 0);
                        totalOdds += (m.team2Odds ?  m.team2Odds.length : 0);
                    });

                    return {
                        matches: matches,
                        total: matches.length,
                        totalOdds: totalOdds,
                        rawElements: allTextData. length,
                        debug: debugInfo,
                        timestamp: new Date().toISOString()
                    };
                }
                return getAllOddsData();
            """)

            if data: 
                self.current_matches = data.get('matches', [])

            return data

        except Exception as e:
            print(f"Error:  {e}")
            return None

    def click_odds_element(self, odds_text, x, y, log_callback):
        try:
            result = self.driver.execute_script(f"""
                var targetValue = '{odds_text}';
                var targetX = {x};
                var targetY = {y};

                var allElements = document.querySelectorAll('*');

                for (var i = 0; i < allElements.length; i++) {{
                    var elem = allElements[i];
                    var text = (elem.innerText || '').trim();

                    if (text === targetValue && elem.offsetWidth > 0 && elem.offsetHeight > 0) {{
                        var rect = elem.getBoundingClientRect();

                        if (Math.abs(rect.x - targetX) < 30 && Math.abs(rect. y - targetY) < 20) {{
                            elem.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                            elem.click();
                            return {{success: true, value: text}};
                        }}
                    }}
                }}

                return {{success: false}};
            """)

            return result

        except Exception as e:
            return {'success': False}

    def place_bet(self, amount, log_callback):
        try:
            time.sleep(1)

            input_result = self.driver.execute_script(f"""
                var amount = {amount};
                var inputs = document.querySelectorAll('input');

                for (var input of inputs) {{
                    var visible = input.offsetWidth > 0 && input.offsetHeight > 0;
                    if (visible && input.type !== 'hidden') {{
                        input.value = '';
                        input.focus();
                        input.value = amount;
                        input. dispatchEvent(new Event('input', {{bubbles: true}}));
                        input.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return {{success: true}};
                    }}
                }}
                return {{success: false}};
            """)

            if not input_result. get('success'):
                log_callback(f"  ⚠ 输入金额失败")
                return False

            log_callback(f"  ✓ 已输入金额:  {amount}")
            time.sleep(0.5)

            confirm_result = self.driver.execute_script("""
                var buttons = document.querySelectorAll('button, div, span, a');

                for (var btn of buttons) {
                    var text = (btn.innerText || '').trim();
                    var visible = btn.offsetWidth > 0 && btn.offsetHeight > 0;

                    if (visible && (text === '下注' || text === '确认' || text === '确定' || text === '投注')) {
                        btn.click();
                        return {success: true, buttonText: text};
                    }
                }
                return {success: false};
            """)

            if confirm_result.get('success'):
                log_callback(f"  ✓ 已点击:  {confirm_result.get('buttonText')}")
                return True

            return False

        except Exception as e:
            log_callback(f"  ✗ 下注出错: {e}")
            return False

    def check_and_auto_bet(self, log_callback):
        if not self.auto_bet_enabled or not self.threshold_settings:
            return

        for match in self.current_matches:
            match_id = match. get('id')
            team1 = match.get('team1', '')
            team2 = match.get('team2', '')

            # 检查所有水位
            for odds in match.get('allOdds', []):
                for setting_key, threshold in self.threshold_settings.items():
                    if threshold and odds['value'] >= threshold:
                        bet_key = f"{match_id}_{odds['text']}_{datetime.now().strftime('%Y%m%d%H%M')}"

                        if bet_key not in self.bet_history:
                            log_callback(f"\n🎯 触发自动下注!")
                            log_callback(f"   比赛: {team1} vs {team2}")
                            log_callback(f"   水位: {odds['text']} (阈值: {threshold})")

                            click_result = self.click_odds_element(odds['text'], odds['x'], odds['y'], log_callback)

                            if click_result.get('success'):
                                if self.place_bet(self.bet_amount, log_callback):
                                    self.bet_history. append(bet_key)
                                    log_callback(f"  ✓✓ 下注成功!  金额: {self.bet_amount} RMB")
                                    return True

        return False

    def monitor_realtime(self, interval, log_callback, update_callback):
        log_callback(f"\n{'='*50}")
        log_callback(f"🚀 开始实时监控水位")
        log_callback(f"   刷新间隔: {interval} 秒")
        log_callback(f"{'='*50}\n")

        while self.is_running:
            try: 
                data = self.get_all_odds_data()

                if data:
                    # 调用update_callback更新GUI
                    update_callback(data)

                    matches = data.get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    log_callback(f"[更新] {len(matches)} 场比赛, {total_odds} 个水位")

                    if self.auto_bet_enabled: 
                        self.check_and_auto_bet(log_callback)

                time.sleep(interval)

            except Exception as e:
                log_callback(f"✗ 监控错误: {str(e)}")
                time. sleep(interval)

        log_callback("\n监控已停止")

    def stop(self):
        self.is_running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
# ================== GUI 类 ==================
class BettingBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("滚球水位实时监控系统")
        self.root.geometry("1900x1000")
        self.root.configure(bg='#1a1a2e')

        self.bot = BettingBot()
        self.monitor_thread = None
        self. threshold_entries = {}
        self.last_update_time = None

        self.create_widgets()

    def create_widgets(self):
        # 标题
        title_frame = tk.Frame(self.root, bg='#1a1a2e')
        title_frame.pack(fill='x', padx=20, pady=10)

        tk.Label(title_frame, text="🎯 滚球水位实时监控系统", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 20, 'bold')).pack()
        tk.Label(title_frame, text="实时更新水位数据 - 显示所有水位值",
                bg='#1a1a2e', fg='#888888', font=('Microsoft YaHei UI', 9)).pack()

        # 主容器
        main_container = tk.Frame(self.root, bg='#1a1a2e')
        main_container.pack(fill='both', expand=True, padx=20, pady=10)

        # 左侧控制面板
        left_frame = tk.Frame(main_container, bg='#16213e', width=420)
        left_frame.pack(side='left', fill='y', padx=(0, 10))
        left_frame.pack_propagate(False)

        # 登录区域
        login_frame = tk.LabelFrame(left_frame, text="🔐 登录", bg='#16213e',
                                   fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold'),
                                   padx=10, pady=10)
        login_frame.pack(fill='x', padx=10, pady=(10, 5))

        tk.Label(login_frame, text="用户名:", bg='#16213e', fg='#ffffff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.username_entry = tk.Entry(login_frame, bg='#0f3460', fg='#ffffff',
                                      font=('Consolas', 10), insertbackground='#ffffff',
                                      relief='flat', width=28)
        self.username_entry.grid(row=0, column=1, pady=3, padx=(5, 0))
        self.username_entry.insert(0, USERNAME)

        tk.Label(login_frame, text="密码:", bg='#16213e', fg='#ffffff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.password_entry = tk.Entry(login_frame, show="*", bg='#0f3460', fg='#ffffff',
                                      font=('Consolas', 10), insertbackground='#ffffff',
                                      relief='flat', width=28)
        self.password_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.password_entry.insert(0, PASSWORD)

        self.login_btn = tk.Button(login_frame, text="登录", bg='#00ff88', fg='#000000',
                                  font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                  command=self.login, cursor='hand2', padx=15, pady=3)
        self.login_btn.grid(row=2, column=0, columnspan=2, pady=(8, 0))

        # 下注设置
        self.bet_frame = tk.LabelFrame(left_frame, text="💰 下注设置", bg='#16213e',
                                      fg='#ff9900', font=('Microsoft YaHei UI', 11, 'bold'),
                                      padx=10, pady=10)

        tk.Label(self.bet_frame, text="下注金额:", bg='#16213e', fg='#ffffff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.amount_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#00ff88',
                                    font=('Consolas', 11, 'bold'), insertbackground='#ffffff',
                                    relief='flat', width=8)
        self.amount_entry. grid(row=0, column=1, pady=3, padx=(5, 0))
        self.amount_entry.insert(0, "2")
        tk.Label(self.bet_frame, text="RMB", bg='#16213e', fg='#888888',
                font=('Microsoft YaHei UI', 9)).grid(row=0, column=2, padx=3)

        tk.Label(self.bet_frame, text="刷新间隔:", bg='#16213e', fg='#ffffff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.interval_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#ffffff',
                                      font=('Consolas', 11), insertbackground='#ffffff',
                                      relief='flat', width=8)
        self.interval_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.interval_entry.insert(0, "3")
        tk.Label(self.bet_frame, text="秒", bg='#16213e', fg='#888888',
                font=('Microsoft YaHei UI', 9)).grid(row=1, column=2, padx=3)

        tk.Label(self.bet_frame, text="水位阈值:", bg='#16213e', fg='#ffffff',
                font=('Microsoft YaHei UI', 10)).grid(row=2, column=0, sticky='w', pady=3)
        self.threshold_entry = tk.Entry(self. bet_frame, bg='#0f3460', fg='#ffaa00',
                                       font=('Consolas', 11), insertbackground='#ffffff',
                                       relief='flat', width=8)
        self.threshold_entry.grid(row=2, column=1, pady=3, padx=(5, 0))
        self.threshold_entry.insert(0, "1. 80")
        tk.Label(self.bet_frame, text="触发", bg='#16213e', fg='#888888',
                font=('Microsoft YaHei UI', 9)).grid(row=2, column=2, padx=3)

        self.auto_bet_var = tk.BooleanVar(value=False)
        self.auto_bet_check = tk.Checkbutton(self.bet_frame, text="启用自动下注",
                                            variable=self.auto_bet_var,
                                            bg='#16213e', fg='#ff4444',
                                            selectcolor='#0f3460',
                                            activebackground='#16213e',
                                            font=('Microsoft YaHei UI', 10, 'bold'),
                                            command=self.toggle_auto_bet)
        self.auto_bet_check.grid(row=3, column=0, columnspan=3, pady=(8, 0), sticky='w')

        # 控制按钮
        self.control_frame = tk.Frame(left_frame, bg='#16213e')

        self.start_btn = tk.Button(self.control_frame, text="🚀 开始监控", bg='#0088ff',
                                   fg='#ffffff', font=('Microsoft YaHei UI', 11, 'bold'),
                                   relief='flat', command=self.start_monitoring,
                                   cursor='hand2', pady=8)
        self.start_btn.pack(fill='x', pady=(0, 5))

        self.stop_btn = tk.Button(self.control_frame, text="⏹ 停止监控", bg='#ff4444',
                                  fg='#ffffff', font=('Microsoft YaHei UI', 11, 'bold'),
                                  relief='flat', command=self.stop_monitoring,
                                  cursor='hand2', pady=8, state='disabled')
        self.stop_btn.pack(fill='x', pady=(0, 5))

        self.refresh_btn = tk.Button(self.control_frame, text="🔄 刷新水位", bg='#666666',
                                    fg='#ffffff', font=('Microsoft YaHei UI', 10),
                                    relief='flat', command=self.refresh_data,
                                    cursor='hand2', pady=6)
        self.refresh_btn.pack(fill='x', pady=(0, 5))

        self.diagnose_btn = tk.Button(self.control_frame, text="🔬 深度诊断", bg='#ff6600',
                                     fg='#ffffff', font=('Microsoft YaHei UI', 10, 'bold'),
                                     relief='flat', command=self. diagnose_page,
                                     cursor='hand2', pady=6)
        self.diagnose_btn.pack(fill='x', pady=(0, 5))

        # 日志区域
        log_frame = tk.LabelFrame(left_frame, text="📋 日志", bg='#16213e',
                                 fg='#888888', font=('Microsoft YaHei UI', 10, 'bold'),
                                 padx=5, pady=5)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.log_text = scrolledtext.ScrolledText(log_frame, bg='#0f3460', fg='#00ff88',
                                                 font=('Consolas', 8), relief='flat',
                                                 height=25, wrap='word')
        self.log_text.pack(fill='both', expand=True)

        # 右侧 - 水位数据区域
        self.right_frame = tk.Frame(main_container, bg='#16213e')
        self.right_frame. pack(side='right', fill='both', expand=True)

        # 水位标题栏
        header_frame = tk.Frame(self.right_frame, bg='#16213e')
        header_frame.pack(fill='x', pady=(0, 5))

        tk.Label(header_frame, text="📊 实时水位数据", bg='#16213e',
                font=('Microsoft YaHei UI', 12, 'bold'), fg='#00ff88').pack(side='left')

        self.update_status_label = tk.Label(header_frame, text="", bg='#16213e',
                font=('Microsoft YaHei UI', 10), fg='#ffaa00')
        self.update_status_label.pack(side='right', padx=10)

        self.hint_label = tk.Label(self.right_frame,
                                  text="请先登录\n\n登录后将显示所有滚球比赛的水位数据\n\n水位数据将实时更新到此区域",
                                  bg='#16213e', fg='#888888',
                                  font=('Microsoft YaHei UI', 11), justify='center')
        self.hint_label.pack(pady=80)

        self.odds_canvas = None
        self.odds_inner_frame = None

        # 状态栏
        status_frame = tk.Frame(self.root, bg='#0f3460', height=30)
        status_frame.pack(side='bottom', fill='x')

        self.status_label = tk.Label(status_frame, text="状态:  未登录", bg='#0f3460',
                                    fg='#888888', font=('Microsoft YaHei UI', 10),
                                    anchor='w', padx=20)
        self.status_label.pack(side='left', fill='y')

        self.time_label = tk.Label(status_frame, text="", bg='#0f3460',
                                  fg='#00ff88', font=('Microsoft YaHei UI', 10),
                                  anchor='e', padx=20)
        self.time_label.pack(side='right', fill='y')

    def create_odds_display_area(self, parent):
        """创建水位显示区域"""
        if self.hint_label: 
            self.hint_label. pack_forget()

        if self.odds_canvas:
            self.odds_canvas.master.destroy()

        canvas_frame = tk.Frame(parent, bg='#16213e')
        canvas_frame.pack(fill='both', expand=True)

        self.odds_canvas = tk. Canvas(canvas_frame, bg='#0f3460', highlightthickness=0)
        scrollbar_y = tk.Scrollbar(canvas_frame, orient='vertical', command=self.odds_canvas.yview)
        scrollbar_x = tk.Scrollbar(canvas_frame, orient='horizontal', command=self.odds_canvas.xview)

        self.odds_inner_frame = tk.Frame(self.odds_canvas, bg='#0f3460')

        self.odds_canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        scrollbar_y.pack(side='right', fill='y')
        scrollbar_x.pack(side='bottom', fill='x')
        self.odds_canvas.pack(side='left', fill='both', expand=True)

        self.canvas_window = self.odds_canvas.create_window((0, 0), window=self.odds_inner_frame, anchor='nw')

        self.odds_inner_frame.bind('<Configure>', lambda e: self.odds_canvas. configure(scrollregion=self. odds_canvas.bbox('all')))
        self.odds_canvas.bind('<Configure>', lambda e: self.odds_canvas.itemconfig(self.canvas_window, width=e.width))
        self.odds_canvas.bind_all('<MouseWheel>', lambda e: self.odds_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

    def update_odds_display(self, data):
        """🆕 更新水位显示到GUI - 修复版：直接显示所有水位"""
        def update():
            try:
                if not self.odds_inner_frame:
                    self.create_odds_display_area(self.right_frame)

                matches = data.get('matches', [])
                total_odds = data.get('totalOdds', 0)
                raw_elements = data.get('rawElements', 0)
                debug = data.get('debug', {})
                timestamp = datetime.now().strftime('%H:%M:%S')

                # 更新时间标签
                self.time_label.config(text=f"最后更新: {timestamp}")
                self.update_status_label.config(text=f"🔄 {timestamp}", fg='#00ff88')
                self.last_update_time = timestamp

                # 清除旧内容
                for widget in self. odds_inner_frame.winfo_children():
                    widget. destroy()

                # 调试信息
                debug_text = f"扫描={debug.get('totalScanned', 0)}, 原始={raw_elements}, 水位={total_odds}"
                tk.Label(self.odds_inner_frame, text=debug_text,
                        bg='#0f3460', fg='#666666', font=('Consolas', 8)).pack(anchor='w', padx=10, pady=2)

                if not matches:
                    tk.Label(self.odds_inner_frame,
                            text="暂无比赛数据，请点击「深度诊断」查看详情",
                            bg='#0f3460', fg='#888888', font=('Microsoft YaHei UI', 11)).pack(pady=20)
                    return

                # 显示统计
                total_team1 = sum(len(m.get('team1Odds', [])) for m in matches)
                total_team2 = sum(len(m.get('team2Odds', [])) for m in matches)
                tk.Label(self.odds_inner_frame,
                        text=f"共 {len(matches)} 场比赛，{total_odds} 个水位 (主队:{total_team1} 客队:{total_team2})",
                        bg='#0f3460', fg='#00ff88', font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w', padx=10, pady=5)

                current_league = ''

                for match in matches:
                    match_id = match.get('id')
                    league = match.get('league', '')
                    team1 = match.get('team1', '未知')
                    team2 = match.get('team2', '未知')
                    score1 = match.get('team1Score', '')
                    score2 = match.get('team2Score', '')
                    time_str = match.get('time', '')
                    team1_odds = match.get('team1Odds', [])
                    team2_odds = match.get('team2Odds', [])
                    all_odds = match.get('allOdds', [])

                    if league and league != current_league:
                        league_frame = tk.Frame(self.odds_inner_frame, bg='#1a1a2e')
                        league_frame.pack(fill='x', pady=(15, 5), padx=5)

                        tk.Label(league_frame, text=f"🏆 {league}", bg='#1a1a2e', fg='#ffaa00',
                                font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w')
                        current_league = league

                    match_title = f"⚽ {score1} {team1} vs {team2} {score2}"
                    if time_str:
                        match_title += f"  ({time_str})"
                    match_title += f"  [主:{len(team1_odds)} 客:{len(team2_odds)}]"

                    match_frame = tk.LabelFrame(self.odds_inner_frame, text=match_title,
                                               bg='#16213e', fg='#00ff88',
                                               font=('Microsoft YaHei UI', 10, 'bold'),
                                               padx=10, pady=8)
                    match_frame. pack(fill='x', padx=5, pady=5)

                    # 🆕 直接显示主队水位
                    if team1_odds:
                        team1_row = tk.Frame(match_frame, bg='#0f3460')
                        team1_row.pack(fill='x', pady=3)
                        
                        tk.Label(team1_row, text=f"主队 {team1[: 15]}:", bg='#0f3460', fg='#888888',
                                font=('Microsoft YaHei UI', 9), width=18, anchor='w').pack(side='left')
                        
                        odds_text = " | ".join([o['text'] for o in team1_odds[: 15]])
                        tk.Label(team1_row, text=odds_text, bg='#0f3460', fg='#00ff88',
                                font=('Consolas', 10, 'bold'), anchor='w').pack(side='left', padx=5)

                    # 🆕 直接显示客队水位
                    if team2_odds:
                        team2_row = tk.Frame(match_frame, bg='#0f3460')
                        team2_row.pack(fill='x', pady=3)
                        
                        tk.Label(team2_row, text=f"客队 {team2[:15]}:", bg='#0f3460', fg='#888888',
                                font=('Microsoft YaHei UI', 9), width=18, anchor='w').pack(side='left')
                        
                        odds_text = " | ".join([o['text'] for o in team2_odds[:15]])
                        tk.Label(team2_row, text=odds_text, bg='#0f3460', fg='#ffaa00',
                                font=('Consolas', 10, 'bold'), anchor='w').pack(side='left', padx=5)

                    # 如果没有区分主客队，显示所有水位
                    if not team1_odds and not team2_odds and all_odds:
                        all_row = tk.Frame(match_frame, bg='#0f3460')
                        all_row.pack(fill='x', pady=3)
                        
                        tk.Label(all_row, text="所有水位:", bg='#0f3460', fg='#888888',
                                font=('Microsoft YaHei UI', 9), width=18, anchor='w').pack(side='left')
                        
                        odds_text = " | ".join([o['text'] for o in all_odds[: 20]])
                        tk.Label(all_row, text=odds_text, bg='#0f3460', fg='#00ff88',
                                font=('Consolas', 10, 'bold'), anchor='w').pack(side='left', padx=5)

                self.odds_inner_frame.update_idletasks()
                self.odds_canvas.configure(scrollregion=self.odds_canvas.bbox('all'))

            except Exception as e:
                print(f"更新显示出错: {e}")
                import traceback
                traceback.print_exc()

        # 使用after确保在主线程中更新GUI
        self.root.after(0, update)

    def log(self, message):
        def update_log():
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_text.insert('end', f"[{timestamp}] {message}\n")
            self.log_text.see('end')
            # 限制日志行数
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 500:
                self.log_text.delete('1.0', '100.0')

        self.root.after(0, update_log)

    def toggle_auto_bet(self):
        if self.auto_bet_var.get():
            if messagebox.askyesno("确认", "确定启用自动下注吗？\n\n水位达到阈值时将自动下注！"):
                self.bot. auto_bet_enabled = True
                # 保存阈值
                try:
                    threshold = float(self.threshold_entry.get())
                    self. bot.threshold_settings['global'] = threshold
                except: 
                    pass
                self. log("⚠️ 自动下注已启用！")
            else:
                self.auto_bet_var.set(False)
        else:
            self.bot.auto_bet_enabled = False
            self.log("自动下注已关闭")

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password: 
            messagebox.showerror("错误", "请输入用户名和密码")
            return

        self.login_btn.config(state='disabled', text="登录中...")
        self.status_label.config(text="状态: 正在登录.. .", fg='#ffaa00')

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

                        # 创建水位显示区域
                        self.create_odds_display_area(self.right_frame)

                        # 自动刷新一次数据
                        self.refresh_data()
                    else:  
                        self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                        self.login_btn.config(state='normal', text="登录")

                self.root.after(0, update_ui)

            except Exception as e:
                self.log(f"登录异常: {str(e)}")
                def update_ui():
                    self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                    self.login_btn.config(state='normal', text="登录")
                self.root.after(0, update_ui)

        threading.Thread(target=login_thread, daemon=True).start()

    def start_monitoring(self):
        try:
            interval = float(self.interval_entry.get())
            amount = float(self.amount_entry.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
            return

        if interval < 1:
            messagebox.showwarning("警告", "刷新间隔不能小于1秒")
            return

        # 保存阈值设置
        try:
            threshold = float(self.threshold_entry.get())
            self.bot.threshold_settings['global'] = threshold
        except:
            pass

        self.bot.bet_amount = amount
        self. bot.auto_bet_enabled = self.auto_bet_var.get()
        self.bot.is_running = True

        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="状态:  监控中.. .", fg='#00ff88')
        self.update_status_label. config(text="🔄 监控中.. .", fg='#00ff88')

        self.log(f"🚀 开始监控，刷新间隔:  {interval}秒")

        # 启动监控线程
        self.monitor_thread = threading.Thread(
            target=self.bot.monitor_realtime,
            args=(interval, self.log, self.update_odds_display),
            daemon=True
        )
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.bot.is_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="状态: 已停止", fg='#ffaa00')
        self.update_status_label.config(text="⏹ 已停止", fg='#ffaa00')
        self.log("监控已停止")

    def diagnose_page(self):
        """深度诊断页面"""
        if not self.bot.driver:
            messagebox.showerror("错误", "请先登录")
            return

        def diagnose_thread():
            self.log("\n" + "="*50)
            self.log("🔬 开始深度诊断...")
            self.log("="*50)

            try:
                # 等待数据加载
                self.bot.wait_for_matches_to_load(self.log)

                # 分析TAHOMA字体
                self.bot.decode_tahoma2_font(self.log)

                # 定位比赛容器
                self.bot.find_match_container(self.log)

                # 获取原始元素
                self.bot.get_raw_elements(self.log)

                # 获取完整数据
                self.log("\n📊 解析比赛数据...")
                data = self.bot.get_all_odds_data()

                if data:
                    matches = data.get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    debug = data.get('debug', {})

                    self.log(f"\n📋 详细数据:")
                    self.log(f"  检测到比赛:  {debug.get('matchesDetected', 0)}")
                    self.log(f"  解析比赛数: {len(matches)}")
                    self.log(f"  总水位数: {total_odds}")
                    self.log(f"  识别球队名:  {debug.get('teamNamesFound', 0)}")
                    self. log(f"  识别水位: {debug.get('oddsFound', 0)}")

                    # 详细输出每场比赛
                    for i, match in enumerate(matches, 1):
                        self. log(f"\n  比赛 {i}:  {match.get('team1', '未知')} vs {match.get('team2', '未知')}")
                        self.log(f"    时间: {match.get('time', '')}")
                        self.log(f"    主队水位数: {len(match.get('team1Odds', []))}")
                        self.log(f"    客队水位数:  {len(match.get('team2Odds', []))}")
                        
                        # 显示主队水位
                        team1_odds = match.get('team1Odds', [])
                        if team1_odds:
                            odds_values = [o['text'] for o in team1_odds[: 10]]
                            self.log(f"    主队水位: {', '.join(odds_values)}")
                        
                        # 显示客队水位
                        team2_odds = match. get('team2Odds', [])
                        if team2_odds:
                            odds_values = [o['text'] for o in team2_odds[:10]]
                            self.log(f"    客队水位: {', '.join(odds_values)}")

                    # 更新GUI显示
                    self.update_odds_display(data)

                self.log("\n" + "="*50)
                self.log("诊断完成！")
                self.log("="*50)

            except Exception as e:
                self.log(f"\n诊断出错: {str(e)}")
                import traceback
                self.log(traceback.format_exc())

        threading.Thread(target=diagnose_thread, daemon=True).start()

    def refresh_data(self):
        def refresh_thread():
            self.log("正在获取水位数据...")

            # 更新状态
            def update_status():
                self. update_status_label.config(text="🔄 刷新中.. .", fg='#ffaa00')
            self.root.after(0, update_status)

            try:
                # 等待加载
                self.bot.wait_for_matches_to_load(self.log)

                # 获取数据
                data = self.bot.get_all_odds_data()

                if data: 
                    matches = data.get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    debug = data.get('debug', {})

                    # 🆕 关键：更新GUI显示
                    self.update_odds_display(data)

                    # 计算主客队水位
                    total_team1 = sum(len(m.get('team1Odds', [])) for m in matches)
                    total_team2 = sum(len(m.get('team2Odds', [])) for m in matches)

                    self.log(f"\n✓ 获取到 {len(matches)} 场比赛, {total_odds} 个水位")
                    self.log(f"  主队水位: {total_team1}, 客队水位: {total_team2}")

                    # 输出每场比赛的水位详情
                    for match in matches:
                        team1 = match.get('team1', '未知')
                        team2 = match.get('team2', '未知')
                        team1_odds = match.get('team1Odds', [])
                        team2_odds = match.get('team2Odds', [])
                        
                        if team1_odds or team2_odds:
                            self.log(f"\n  {team1} vs {team2}:")
                            if team1_odds:
                                odds_str = ', '.join([o['text'] for o in team1_odds[:8]])
                                self.log(f"    主队:  {odds_str}")
                            if team2_odds:
                                odds_str = ', '.join([o['text'] for o in team2_odds[:8]])
                                self.log(f"    客队: {odds_str}")

                    if total_odds == 0:
                        self. log("\n⚠️ 未获取到水位数据，点击「深度诊断」查看原因")
                else:
                    self.log("❌ 未获取到数据")

            except Exception as e:
                self.log(f"刷新失败: {e}")
                import traceback
                self.log(traceback.format_exc())

        threading.Thread(target=refresh_thread, daemon=True).start()

    def on_closing(self):
        if messagebox.askokcancel("退出", "确定退出？"):
            self.bot.stop()
            self.root.destroy()


# ================== 主程序 ==================
if __name__ == "__main__":
    root = tk. Tk()
    app = BettingBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
