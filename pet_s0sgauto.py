#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
채팅 로그(chat.txt)에서 스톤에이지 페트 정보를 추출해서 JSON으로 만드는 스크립트 v2

1) 하는 일
   - "[이름] [1등급] 페트 검색 결과 입니다." 형태에서
       * name  : 페트 이름
       * grade : "최상급"(1등급), "상급"(2등급), "일반"(표시 없음 또는 그 외)
   - "초기 : 레벨 1, 공격력 A, 방어력 D, 순발력 G, 내구력 H"
       * s0: { "atk": A, "def": D, "agi": G, "hp": H }
   - "성장 : 공격력 a, 방어력 d, 순발력 g, 성장 t, 내구력 h"
       * sg: { "atk": a, "def": d, "agi": g, "hp": h }
   - "기술 : …, 속성 : 화6 수4 , …, 경로 : 쟈루 섬(동357 남183) 포획"
       * attr : {"지":?, "수":?, "화":?, "풍":?}
       * route: "쟈루 섬(동357 남183) 포획"

2) 사용법 예시
   # 순수 추출 결과만 보고 싶을 때 (stdout 출력)
   python pet_s0sgauto_v2.py chat.txt

   # 추출 결과를 json 파일로 저장
   python pet_s0sgauto_v2.py chat.txt -o pets_extracted.json

   # 기존 pets.json 에 병합해서 저장
   #  - pets.json 이 {"이름": {...}, ...} 딕셔너리여도 되고
   #    [{...}, ...] 리스트여도 됨.
   python pet_s0sgauto_v2.py chat.txt --merge pets.json -o pets_merged.json
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any


HEADER_RE = re.compile(
    r"^\[(?P<name>[^\]]+)\]\s*(?:\[(?P<grade>\d)등급\]\s*)?페트 검색 결과 입니다\."
)

INIT_RE = re.compile(
    r"초기\s*:\s*레벨\s*:?[\s\d]*,"
    r"\s*공격력\s*(?P<atk>\d+),"
    r"\s*방어력\s*(?P<def>\d+),"
    r"\s*순발력\s*(?P<agi>\d+),"
    r"\s*내구력\s*(?P<hp>\d+)"
)

GROW_RE = re.compile(
    r"성장\s*:\s*공격력\s*(?P<atk>\d+(?:\.\d+)?),"
    r"\s*방어력\s*(?P<def>\d+(?:\.\d+)?),"
    r"\s*순발력\s*(?P<agi>\d+(?:\.\d+)?),"
    r"\s*성장\s*\d+(?:\.\d+)?,"  # 총 성장값은 버림
    r"\s*내구력\s*(?P<hp>\d+(?:\.\d+)?)"
)

ATTR_SEG_RE = re.compile(r"속성\s*:\s*([^,]+)")
ATTR_TOKEN_RE = re.compile(r"([지수화풍])\s*(\d+)")
ROUTE_RE = re.compile(r"경로\s*:\s*(.+)")


def grade_digit_to_str(d: str | None) -> str:
    """1→최상급, 2→상급, 나머지/없음→일반"""
    if d == "1":
        return "최상급"
    if d == "2":
        return "상급"
    return "일반"


def parse_chat(text: str) -> Dict[str, Dict[str, Any]]:
    pets: Dict[str, Dict[str, Any]] = {}
    current: Dict[str, Any] | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # 1) 헤더 라인: [이름] [1등급] 페트 검색 결과 입니다.
        m = HEADER_RE.search(line)
        if m:
            name = m.group("name").strip()
            g_digit = m.group("grade")
            g_str = grade_digit_to_str(g_digit)

            if name not in pets:
                pets[name] = {"name": name}
            current = pets[name]

            # 등급은 "일반"보다 높은 값이 나왔으면 덮어쓰기 허용
            if g_digit is not None or "grade" not in current:
                current["grade"] = g_str
            continue

        # 헤더가 한 번도 안 나온 상태라면 스킵
        if current is None:
            continue

        # 2) 초기치
        m = INIT_RE.search(line)
        if m:
            s0 = {
                "atk": int(m.group("atk")),
                "def": int(m.group("def")),
                "agi": int(m.group("agi")),
                "hp": int(m.group("hp")),
            }
            current.setdefault("s0", {}).update(s0)
            continue

        # 3) 성장률
        m = GROW_RE.search(line)
        if m:
            sg = {
                "atk": float(m.group("atk")),
                "def": float(m.group("def")),
                "agi": float(m.group("agi")),
                "hp": float(m.group("hp")),
            }
            current.setdefault("sg", {}).update(sg)
            continue

        # 4) 기술/속성/경로
        if "기술" in line and "속성" in line:
            # 4-1) 속성
            m_attr = ATTR_SEG_RE.search(line)
            if m_attr:
                seg = m_attr.group(1)
                attr = {"지": 0, "수": 0, "화": 0, "풍": 0}
                for tok in seg.split():
                    tok = tok.strip()
                    if not tok:
                        continue
                    m_tok = ATTR_TOKEN_RE.match(tok)
                    if not m_tok:
                        continue
                    el, val = m_tok.groups()
                    attr[el] = int(val)
                if any(v > 0 for v in attr.values()):
                    current["attr"] = attr

            # 4-2) 경로
            m_route = ROUTE_RE.search(line)
            if m_route:
                route = m_route.group(1).strip()
                current["route"] = route

    return pets


def merge_into_pets(base_path: Path, patch: Dict[str, Dict[str, Any]]):
    """
    기존 pets.json 에 patch 내용을 병합.
    - pets.json 이 dict 형태({"이름": {...}})면 같은 구조로 반환
    - pets.json 이 list 형태([{...}, ...])면 리스트로 반환
    """
    data = json.loads(base_path.read_text(encoding="utf-8"))

    # dict 형태: {"이름": { ... }, ... }
    if isinstance(data, dict):
        for name, extra in patch.items():
            target = data.get(name)
            if target is None:
                target = {}
                data[name] = target
            if not isinstance(target, dict):
                continue
            # 병합
            for key in ("grade", "s0", "sg", "attr", "route"):
                if key not in extra:
                    continue
                if isinstance(extra[key], dict) and isinstance(target.get(key), dict):
                    target[key].update(extra[key])
                else:
                    target[key] = extra[key]
        return data

    # list 형태: [{...}, ...]
    if isinstance(data, list):
        by_name: Dict[str, dict] = {}
        for obj in data:
            if isinstance(obj, dict) and "name" in obj:
                by_name[obj["name"]] = obj

        for name, extra in patch.items():
            target = by_name.get(name)
            if not target:
                new_obj = {"name": name}
                for key in ("grade", "s0", "sg", "attr", "route"):
                    if key in extra:
                        new_obj[key] = extra[key]
                data.append(new_obj)
                continue

            for key in ("grade", "s0", "sg", "attr", "route"):
                if key in extra:
                    if isinstance(extra[key], dict) and isinstance(target.get(key), dict):
                        target[key].update(extra[key])
                    else:
                        target[key] = extra[key]
        return data

    raise ValueError("pets.json 형식을 알 수 없습니다. dict 또는 list 여야 합니다.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="chat.txt에서 페트 s0/sg/등급/속성/경로를 추출해 JSON으로 변환"
    )
    p.add_argument("chat", help="채팅 로그 txt 파일 경로 (예: chat.txt)")
    p.add_argument(
        "-o", "--out",
        help="결과 JSON 파일 경로 (생략 시 stdout으로 출력)"
    )
    p.add_argument(
        "--merge",
        metavar="PETS_JSON",
        help="기존 pets.json 파일 경로 (지정하면 해당 파일에 병합)"
    )

    args = p.parse_args(argv)

    chat_path = Path(args.chat)
    if not chat_path.is_file():
        p.error(f"채팅 로그 파일을 찾을 수 없습니다: {chat_path}")

    text = chat_path.read_text(encoding="utf-8")
    parsed = parse_chat(text)

    # 기본 출력은 "이름 기준 정렬된 리스트"
    extracted_list: list[dict] = []
    for name in sorted(parsed.keys(), key=lambda s: s):
        obj = parsed[name].copy()
        obj["name"] = name
        extracted_list.append(obj)

    if args.merge:
        base_path = Path(args.merge)
        if not base_path.is_file():
            p.error(f"merge 대상 pets.json 파일을 찾을 수 없습니다: {base_path}")
        result = merge_into_pets(base_path, parsed)
    else:
        result = extracted_list

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"저장 완료: {out_path}")
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
