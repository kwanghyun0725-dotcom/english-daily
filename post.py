"""Instagram Graph API 게시 (컨테이너 생성 -> 상태 확인 -> 발행)."""
import os
import time

import requests

API_VERSION = os.environ.get("IG_API_VERSION", "v26.0")
# Instagram 로그인 방식: graph.instagram.com / 페이스북 로그인 방식: graph.facebook.com
API_BASE = os.environ.get("IG_API_BASE", "https://graph.instagram.com")


def _url(path):
    return f"{API_BASE}/{API_VERSION}/{path}"


def _check(r, what):
    if not r.ok:
        raise RuntimeError(f"{what} 실패 [{r.status_code}]: {r.text}")
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{what} 실패: {data['error']}")
    return data


def create_container(ig_user_id, token, image_url, caption):
    r = requests.post(
        _url(f"{ig_user_id}/media"),
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=60,
    )
    return _check(r, "컨테이너 생성")["id"]


def wait_ready(container_id, token, timeout=180):
    """status_code 가 FINISHED 가 될 때까지 대기."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(
            _url(container_id),
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        data = _check(r, "컨테이너 상태 확인")
        last = data.get("status_code")
        if last == "FINISHED":
            return True
        if last == "ERROR":
            raise RuntimeError(f"이미지 처리 실패: {data.get('status')}")
        time.sleep(5)
    raise RuntimeError(f"컨테이너 처리 시간 초과 (마지막 상태: {last})")


def publish(ig_user_id, token, container_id):
    r = requests.post(
        _url(f"{ig_user_id}/media_publish"),
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    return _check(r, "게시")["id"]


def post_image(ig_user_id, token, image_url, caption):
    cid = create_container(ig_user_id, token, image_url, caption)
    print(f"  컨테이너 생성됨: {cid}")
    wait_ready(cid, token)
    media_id = publish(ig_user_id, token, cid)
    print(f"  게시 완료: {media_id}")
    return media_id
