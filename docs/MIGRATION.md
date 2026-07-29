# 우분투 서버 폐지 & GitHub 인프라 이전 가이드

기존 개인 우분투 서버를 폐지하고 GitHub 인프라로 이전할 때의 **정직한 구조**와
단계별 방법을 정리합니다.

---

## 1. 무엇이 GitHub로 가능하고, 무엇이 불가능한가

| 구성요소 | 성격 | GitHub Pages/Actions 이전 | 결론 |
| :--- | :--- | :--- | :--- |
| 자동매매 엔진 (`main.py`) | 상시 구동·2초 스캘핑·실시간 손절 | 불가 (Actions는 일시 실행·최소 5분·지연/누락) | **상시 호스트 필요** |
| Streamlit 대시보드 (`dashboard.py`) | 파이썬 서버 | 불가 (Pages는 정적만) | 정적 JS로 대체 |
| 시장 국면(200일선) 표시 | 공개 데이터 조회 후 표시 | **가능** | Pages + Actions |

### ⚠️ 핵심 주의: GitHub Secrets는 브라우저에서 읽을 수 없습니다
- Secrets는 **GitHub Actions(서버측 러너)** 안에서만 사용 가능합니다.
- 정적 Pages(브라우저 JS)에 KIS 키를 넣으면 **페이지 소스에 그대로 노출**됩니다. 절대 금지.
- 따라서 KIS 키가 필요한 작업은 **오직 Actions 워크플로 안**에서만 수행하고, 그 결과(JSON)만 Pages로 내보냅니다.

### ⚠️ 핵심 주의: Actions로 실계좌 스캘핑은 위험합니다
- 예약(cron) 실행은 GitHub 부하에 따라 **수 분~수십 분 지연되거나 누락**됩니다(best-effort).
- 급락장에서 손절 실행이 늦어지면 **실제 금전 손실**로 이어집니다.
- 실매매 봇은 반드시 **상시 구동 호스트**에서 돌리세요.

---

## 2. 권장 구조 (A안): 무료 상시 VM + GitHub 정적 대시보드

```
[무료 상시 VM]  트레이딩 엔진 실행 (코드/전략 그대로, .env 사용)
      │  (선택) 거래 요약 JSON을 리포지토리에 push
      ▼
[GitHub Actions cron]  scripts/build_market_regime.py 주기 실행 (비밀키 불필요)
      │  docs/data/market_regime.json 커밋
      ▼
[GitHub Pages: docs/]  정적 JS 대시보드가 JSON을 fetch 하여 표시
      → https://leemgs.github.io/stock-quant-trader-kis/regime.html
```

"내 물리 서버 관리"에서는 벗어나면서, 손절 등 **안전 필수 실시간성**은 유지하는 방법입니다.

### 2-1. 트레이딩 엔진을 옮길 무료 상시 호스트 후보
- **Oracle Cloud Always-Free** — 진짜 상시 무료 VM(Ampere/AMD). 가장 추천.
- GCP `e2-micro` 무료 티어, AWS 프리티어(12개월), Fly.io, 집의 라즈베리파이 등.

### 2-2. Oracle Cloud 예시 이전 절차 (개요)
1. Oracle Cloud 가입 → Always-Free 대상 VM(Ubuntu 22.04) 생성.
2. SSH 접속 후 저장소 클론:
   ```bash
   git clone https://github.com/leemgs/stock-quant-trader-kis.git
   cd stock-quant-trader-kis
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. `.env` 생성(기존 우분투 서버의 값 그대로 복사). `.env`는 절대 커밋하지 않습니다(`.gitignore` 확인).
4. `systemd` 또는 `docker compose`로 상시 실행 (README의 옵션 C/D 참고).
5. 기존 우분투 서버 폐지.

> 즉, `.env` 환경변수는 **그대로 재사용**하되, 이제는 폐지한 내 서버가 아니라 무료 상시 VM에 둡니다.

---

## 3. 대안 구조 (B안): Actions 저빈도 크론 트레이더 (전략 격하 · 위험 감수)

상시 VM조차 두기 싫다면, 스캘핑을 포기하고 **5~15분 주기 스윙 매매**로 재설계할 수 있습니다.
- 매 실행: 상태 로드 → 시세 조회 → 매수/매도 판단 → 주문 → 상태 저장 → 종료(stateless).
- KIS 키는 **GitHub Secrets**, 포지션 상태는 private 저장소 또는 외부 무료 DB에 영속화.
- **위험**: 크론 지연/누락 시 손절 미실행. 실계좌 적용 전 반드시 모의투자로 검증.
- 코드 재작성 규모가 크며, 본 가이드 범위에서는 스캐폴딩만 별도 논의합니다.

---

## 4. GitHub Pages 설정 (정적 대시보드 공개)

1. 리포지토리 **Settings → Pages** 이동.
2. **Build and deployment → Source: "Deploy from a branch"** 선택.
3. **Branch: `main`, Folder: `/docs`** 선택 후 Save.
4. 잠시 후 아래 주소로 공개됩니다:
   - 홈: `https://leemgs.github.io/stock-quant-trader-kis/`
   - 시장 국면: `https://leemgs.github.io/stock-quant-trader-kis/regime.html`

### 자동 갱신 워크플로
- `.github/workflows/update-market-regime.yml` 가 2시간마다(및 수동 실행 시)
  `scripts/build_market_regime.py` 를 돌려 `docs/data/market_regime.json` 을 갱신·커밋합니다.
- 야후 공개 데이터만 쓰므로 **비밀키가 필요 없습니다.**
- Actions 탭 → "Update Market Regime Data" → **Run workflow** 로 즉시 갱신 가능.

---

## 5. 보안·프라이버시 체크리스트
- [ ] `.env` 는 커밋 금지(민감정보). 서버/VM에만 둔다.
- [ ] KIS 키 등 비밀은 **GitHub Secrets**(Actions 전용)로만. 프론트엔드 JS에 절대 넣지 않는다.
- [ ] 계좌 잔고·실현손익 등 **재무정보는 공개 Pages에 게시하지 않는다**(공개 저장소는 전 세계에 노출).
- [ ] 시장 국면 같은 **공개 데이터**만 정적 대시보드로 공개한다.
