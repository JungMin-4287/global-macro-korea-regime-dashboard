# 글로벌 매크로 레짐·한국 주도주 대시보드

KOSPI·KOSDAQ의 50일/120일 이격도 지수, 252거래일 MDD·현재 낙폭, 시장 폭, 삼성전자·SK하이닉스의 30일 이격도와 중단기 트레이딩 신호를 HTML 차트로 자동 갱신하는 프로젝트입니다.

## 핵심 계산

- 이격도 지수 = `현재가 / 이동평균 * 100`
- 괴리율(%) = `이격도 지수 - 100`
- 지수: 50일·120일 이격도
- 삼성전자·SK하이닉스: 30일 이격도(전술) + 50·120일선과 252일 MDD(중기)
- 호재에도 하락하면 경고, 악재에도 전저점을 지키면 바닥 선행 신호

## 단일 실행 진입점

대시보드 갱신은 루트의 `update_dashboard.py`만 실행합니다. `scripts/update_dashboard_v*.py` 파일은 최신 기능을 구성하는 내부 호환 모듈이며 GitHub Actions나 로컬 사용자가 직접 실행하지 않습니다.

## 자동 갱신

GitHub Actions가 평일 한국시간 09:00~15:45에 15분 간격으로 실행되며, 15:40 종가 갱신과 다음 날 05:30 미국장 마감 갱신을 추가 수행합니다.

1. KRX(pykrx)를 우선 사용
2. 실패하면 Yahoo Finance를 대체 소스로 사용
3. `docs/data/market_data.json`, `docs/data/market_history.csv`, `docs/index.html` 갱신
4. 변경 내용을 자동 커밋

## 로컬 실행

```bash
pip install -r requirements.txt
python update_dashboard.py
python -m http.server 8000 -d docs
```

브라우저에서 `http://localhost:8000`을 엽니다.

## GitHub Pages

Repository Settings → Pages → **Deploy from a branch** → `main` / `/docs`를 선택하면 대시보드 URL은 다음 형식입니다.

`https://jungmin-4287.github.io/global-macro-korea-regime-dashboard/`

비공개 저장소의 Pages 사용 가능 여부는 GitHub 요금제에 따라 다를 수 있습니다.

## 수동 보강 데이터

`docs/data/manual_signals.json`에 신용융자, 미수금·반대매매, AI CAPEX, 메모리 가격의 2차 미분, 금리·신용 신호를 입력할 수 있습니다.
