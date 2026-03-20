#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import time
import threading
from datetime import datetime

import schedule
from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)
config_lock = threading.Lock()


def load_config():
    """설정 파일 읽기"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    """설정 파일 저장"""
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_day_of_week():
    """요일 가져오기 (월~일)"""
    days = ['월', '화', '수', '목', '금', '토', '일']
    return days[datetime.now().weekday()]


def post_to_board(driver, config, title):
    """Selenium으로 로그인 후 게시글 작성"""
    sel = config['selectors']
    wait = WebDriverWait(driver, 15)

    # 로그인
    driver.get(config['login_url'])
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel['username_input'])))
    driver.find_element(By.CSS_SELECTOR, sel['username_input']).send_keys(config['username'])
    driver.find_element(By.CSS_SELECTOR, sel['password_input']).send_keys(config['password'])
    driver.find_element(By.CSS_SELECTOR, sel['login_button']).click()
    wait.until(EC.url_changes(config['login_url']))

    # 글쓰기 페이지 이동
    driver.get(config['write_url'])
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel['title_input'])))
    driver.find_element(By.CSS_SELECTOR, sel['title_input']).send_keys(title)
    driver.find_element(By.CSS_SELECTOR, sel['content_input']).send_keys(".")
    driver.find_element(By.CSS_SELECTOR, sel['submit_button']).click()


def create_post():
    """게시글 생성 및 포스팅"""
    with config_lock:
        config = load_config()
        serial = config['current_serial']
        day = get_day_of_week()
        title = f"{serial} {day}"

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print(f"제목: {title}")
        print(f"본문: .")

        # Selenium headless 브라우저 실행
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=chrome_options)
        try:
            post_to_board(driver, config, title)
        finally:
            driver.quit()

        # 로그 저장
        os.makedirs('logs', exist_ok=True)
        log_file = f"logs/{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] Posted: {title}\n")

        # 일련번호 증가
        config['current_serial'] = serial + 1
        save_config(config)

    print(f"게시 완료! 다음 번호: {config['current_serial']}")


# --- Flask API ---

@app.route('/serial', methods=['GET'])
def get_serial():
    with config_lock:
        config = load_config()
    return jsonify({'current_serial': config['current_serial']})


@app.route('/serial', methods=['PUT'])
def set_serial():
    data = request.get_json()
    if not data or 'value' not in data:
        return jsonify({'error': 'value 필드가 필요합니다'}), 400
    with config_lock:
        config = load_config()
        config['current_serial'] = int(data['value'])
        save_config(config)
    return jsonify({'current_serial': config['current_serial']})


@app.route('/serial/increment', methods=['POST'])
def increment_serial():
    with config_lock:
        config = load_config()
        config['current_serial'] += 1
        save_config(config)
    return jsonify({'current_serial': config['current_serial']})


@app.route('/post', methods=['POST'])
def trigger_post():
    t = threading.Thread(target=create_post, daemon=True)
    t.start()
    return jsonify({'message': '포스팅이 시작되었습니다.'}), 202


def run_api_server():
    app.run(host='0.0.0.0', port=5000, use_reloader=False)


def main():
    config = load_config()

    # Flask API 서버를 별도 스레드로 실행
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    print(f"API 서버 시작: http://localhost:5000")

    # 스케줄 등록
    schedule.every().day.at(config['post_time']).do(create_post)
    print(f"스케줄 등록: 매일 {config['post_time']} 자동 포스팅")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
