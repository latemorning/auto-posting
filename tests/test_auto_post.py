#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import sys

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auto_post
from auto_post import app, get_day_of_week, load_config, save_config, post_to_board, create_post

SAMPLE_CONFIG = {
    "current_serial": 100,
    "board_url": "http://example.com/board",
    "post_time": "09:00",
    "login_url": "http://example.com/login",
    "write_url": "http://example.com/write",
    "username": "testuser",
    "password": "testpass",
    "selectors": {
        "username_input": "#username",
        "password_input": "#password",
        "login_button": "#login-btn",
        "title_input": "#title",
        "content_input": "#content",
        "submit_button": "#submit",
    },
}


@pytest.fixture
def tmp_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(tmp_config, monkeypatch):
    monkeypatch.chdir(tmp_config)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# --- 1. get_day_of_week() ---

class TestGetDayOfWeek:
    @pytest.mark.parametrize("weekday,expected", [
        (0, "월"), (1, "화"), (2, "수"), (3, "목"),
        (4, "금"), (5, "토"), (6, "일"),
    ])
    def test_all_days(self, weekday, expected):
        mock_dt = MagicMock()
        mock_dt.weekday.return_value = weekday
        with patch("auto_post.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            assert get_day_of_week() == expected


# --- 2. load_config() / save_config() ---

class TestConfigIO:
    def test_load_config(self, tmp_config, monkeypatch):
        monkeypatch.chdir(tmp_config)
        assert load_config() == SAMPLE_CONFIG

    def test_save_then_load_retains_serial(self, tmp_config, monkeypatch):
        monkeypatch.chdir(tmp_config)
        config = load_config()
        config["current_serial"] = 999
        save_config(config)
        assert load_config()["current_serial"] == 999


# --- 3. post_to_board() ---

class TestPostToBoard:
    def test_driver_get_order(self):
        driver = MagicMock()
        with patch("auto_post.WebDriverWait"):
            post_to_board(driver, SAMPLE_CONFIG, "100 월")

        get_calls = driver.get.call_args_list
        assert get_calls[0] == call(SAMPLE_CONFIG["login_url"])
        assert get_calls[1] == call(SAMPLE_CONFIG["write_url"])

    def test_send_keys_and_click_counts(self):
        driver = MagicMock()
        with patch("auto_post.WebDriverWait"):
            post_to_board(driver, SAMPLE_CONFIG, "100 월")

        # username, password, title, content → 4 send_keys calls
        assert driver.find_element.return_value.send_keys.call_count == 4
        # login_button, submit_button → 2 click calls
        assert driver.find_element.return_value.click.call_count == 2


# --- 4. create_post() ---

FIXED_DT = datetime(2026, 3, 20, 9, 0, 0)  # Friday (weekday=4, 금)


def _patch_create_post(monkeypatch_chdir, tmp_config, extra_patches=None):
    """create_post() 실행에 필요한 공통 패치 컨텍스트를 반환하는 헬퍼."""
    monkeypatch_chdir.chdir(tmp_config)


class TestCreatePost:
    def _run_create_post(self, tmp_config, monkeypatch, side_effect=None):
        monkeypatch.chdir(tmp_config)
        mock_driver = MagicMock()
        captured_titles = []

        def fake_post(driver, config, title):
            captured_titles.append(title)

        patches = [
            patch("auto_post.webdriver.Chrome", return_value=mock_driver),
            patch("auto_post.WebDriverWait"),
            patch("auto_post.post_to_board", side_effect=fake_post),
            patch("auto_post.datetime") ,
        ]
        with patches[0], patches[1], patches[2], patches[3] as mock_datetime:
            mock_datetime.now.return_value = FIXED_DT
            create_post()

        return captured_titles

    def test_log_file_created(self, tmp_config, monkeypatch):
        self._run_create_post(tmp_config, monkeypatch)
        log_file = tmp_config / "logs" / "20260320.log"
        assert log_file.exists()

    def test_log_file_contains_title(self, tmp_config, monkeypatch):
        self._run_create_post(tmp_config, monkeypatch)
        log_file = tmp_config / "logs" / "20260320.log"
        content = log_file.read_text(encoding="utf-8")
        assert "100" in content

    def test_serial_incremented(self, tmp_config, monkeypatch):
        self._run_create_post(tmp_config, monkeypatch)
        monkeypatch.chdir(tmp_config)
        assert load_config()["current_serial"] == 101

    def test_title_format(self, tmp_config, monkeypatch):
        titles = self._run_create_post(tmp_config, monkeypatch)
        assert len(titles) == 1
        assert re.match(r"^\d+ [월화수목금토일]$", titles[0])


# --- 5–8. Flask API ---

class TestFlaskAPI:
    def test_get_serial_status_and_key(self, client):
        resp = client.get("/serial")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "current_serial" in data
        assert data["current_serial"] == 100

    def test_put_serial_sets_value(self, client):
        resp = client.put("/serial", json={"value": 9999})
        assert resp.status_code == 200
        assert resp.get_json()["current_serial"] == 9999

    def test_put_serial_reflected_in_get(self, client):
        client.put("/serial", json={"value": 9999})
        assert client.get("/serial").get_json()["current_serial"] == 9999

    def test_put_serial_no_body_returns_4xx(self, client):
        # Flask returns 415 when Content-Type is missing, 400 when body is invalid JSON
        resp = client.put("/serial")
        assert resp.status_code >= 400

    def test_put_serial_missing_value_key_returns_400(self, client):
        resp = client.put("/serial", json={"wrong_key": 123})
        assert resp.status_code == 400

    def test_increment_serial_returns_plus_one(self, client):
        initial = client.get("/serial").get_json()["current_serial"]
        resp = client.post("/serial/increment")
        assert resp.status_code == 200
        assert resp.get_json()["current_serial"] == initial + 1

    def test_increment_serial_twice_returns_plus_two(self, client):
        initial = client.get("/serial").get_json()["current_serial"]
        client.post("/serial/increment")
        resp = client.post("/serial/increment")
        assert resp.get_json()["current_serial"] == initial + 2

    def test_trigger_post_returns_202(self, client):
        with patch("auto_post.threading.Thread") as mock_thread:
            resp = client.post("/post")
        assert resp.status_code == 202
        assert resp.get_json()["message"] == "포스팅이 시작되었습니다."
        mock_thread.assert_called_once_with(target=create_post, daemon=True)
        mock_thread.return_value.start.assert_called_once()
