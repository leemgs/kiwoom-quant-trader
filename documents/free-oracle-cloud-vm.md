# ☁️ 무료 Open Cloud VM에서 24시간 운영하기 (Oracle Cloud Always-Free)

개인 PC나 우분투 서버를 계속 켜두기 부담스럽다면, **무료로 상시(24/7) 켜지는 클라우드 VM**에
매매 봇을 올려 운영할 수 있습니다. 이 문서는 **Oracle Cloud Always-Free**를 기준으로 설명하지만,
GCP `e2-micro` 무료 티어 · AWS 프리티어 등 다른 무료 VM에도 동일하게 적용됩니다.

> ⚠️ **왜 "상시 VM"이 필요한가**
> 본 봇은 장중에 2초 주기로 시세를 감시하고 실시간으로 손절/트레일링 스탑을 집행합니다.
> 이런 실시간·상시 구동은 GitHub Actions 같은 "일시 실행" 인프라로 대체할 수 없습니다
> (크론 최소 5분·지연/누락·상태 비영속). 따라서 **항상 켜져 있는 호스트**가 반드시 필요하며,
> 무료 상시 VM이 개인 서버를 대체하는 가장 현실적인 선택지입니다.

---

## 0. 무료 VM 후보 비교

| 제공사 | 무료 등급 | 상시 구동 | 사양(대략) | 비고 |
| :--- | :--- | :---: | :--- | :--- |
| **Oracle Cloud** | **Always-Free** | ✅ (기한 없음) | Ampere ARM 최대 4 OCPU/24GB 또는 AMD 1/1GB×2 | 가장 넉넉함. **추천** |
| Google Cloud | Free Tier | ✅ (기한 없음) | `e2-micro` 1 vCPU/1GB (특정 리전) | 리전 제한 |
| AWS | Free Tier | ✅ (12개월) | `t2.micro`/`t3.micro` 1 vCPU/1GB | 12개월 후 과금 |

> 파이썬 봇 + Streamlit 대시보드는 1 vCPU / 1GB 램으로도 충분히 돌아갑니다.

---

## 1. Oracle Cloud 가입 및 VM 생성

1. [Oracle Cloud 가입](https://www.oracle.com/cloud/free/) → 신용카드 본인확인(과금 없음, Always-Free 유지).
2. 콘솔에서 **Compute → Instances → Create Instance**.
3. 설정:
   - **Image**: Canonical Ubuntu 22.04
   - **Shape**: `VM.Standard.A1.Flex`(ARM Ampere, Always-Free) — OCPU 1~2, 메모리 6GB 정도면 충분
     - ARM 재고가 없으면 `VM.Standard.E2.1.Micro`(AMD, Always-Free)를 선택
   - **SSH 키**: 로컬에서 `ssh-keygen`으로 만든 공개키 등록(또는 콘솔에서 키 생성 후 개인키 저장)
4. **Create** 클릭 → 인스턴스의 **Public IP** 확인.

### 방화벽(포트) 열기
대시보드(8501)를 외부에서 보려면 두 곳을 모두 열어야 합니다.
1. **VCN Security List / NSG** (콘솔): Ingress 규칙에 `TCP 8501` 허용 추가.
2. **인스턴스 OS 방화벽**:
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8501 -j ACCEPT
   sudo netfilter-persistent save    # 재부팅 후에도 유지 (없으면: sudo apt install iptables-persistent)
   ```
> 대시보드에 계좌·손익 등 민감정보가 표시되므로, 가능하면 8501을 전체 공개하지 말고
> 본인 IP만 허용하거나 SSH 터널(`ssh -L 8501:localhost:8501 ...`)로 접속하세요.

---

## 2. SSH 접속 및 프로젝트 설치

```bash
# 로컬에서 접속 (ubuntu 계정이 기본)
ssh -i ~/.ssh/your_key ubuntu@<PUBLIC_IP>

# 필수 패키지
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

# 저장소 클론
git clone https://github.com/leemgs/stock-quant-trader-kis.git
cd stock-quant-trader-kis

# 가상환경 + 의존성
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. `.env` 설정 (기존 값 그대로 재사용)

기존 서버에서 쓰던 `.env`를 그대로 복사해 옵니다. `.env`는 **절대 GitHub에 커밋하지 않습니다**
(`.gitignore`에 이미 포함).

```bash
cp .env.sample .env
nano .env      # KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO 등 입력
```

- 로컬 PC의 기존 `.env`를 업로드하려면:
  ```bash
  scp -i ~/.ssh/your_key ./.env ubuntu@<PUBLIC_IP>:~/stock-quant-trader-kis/.env
  ```
- 환경변수 상세는 [environment-variables.md](./environment-variables.md) 참고.

> 🔐 **보안 원칙**: KIS 키 같은 비밀은 오직 이 VM의 `.env`(또는 CI라면 GitHub Secrets)에만 둡니다.
> 공개 웹페이지/프론트엔드 JS에는 절대 넣지 마세요.

---

## 4. 상시 실행 (systemd 권장)

VM이 재부팅되어도 자동으로 봇이 살아나도록 systemd 서비스로 등록합니다.
(경로/계정은 본인 환경에 맞게 수정 — 아래는 `ubuntu` 계정, 홈에 클론한 경우)

```bash
sudo tee /etc/systemd/system/kis-trader.service > /dev/null << 'EOF'
[Unit]
Description=KIS Quant Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/stock-quant-trader-kis
ExecStart=/home/ubuntu/stock-quant-trader-kis/.venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now kis-trader
```

대시보드도 상시 띄우려면:
```bash
sudo tee /etc/systemd/system/kis-dashboard.service > /dev/null << 'EOF'
[Unit]
Description=KIS Trading Dashboard (Streamlit)
After=network-online.target kis-trader.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/stock-quant-trader-kis
ExecStart=/home/ubuntu/stock-quant-trader-kis/.venv/bin/python -m streamlit run src/monitor/dashboard.py --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now kis-dashboard
```

> Docker를 선호한다면 systemd 대신 `docker-compose up -d`도 가능합니다.
> 자세한 실행 옵션(A~D)은 [installation-and-run.md](./installation-and-run.md) 참고.

### 운영 명령어
```bash
systemctl status kis-trader          # 상태 확인
journalctl -u kis-trader -f          # 실시간 로그
sudo systemctl restart kis-trader    # .env 수정 후 반영
```

---

## 5. 접속 및 확인

- **대시보드**: 브라우저에서 `http://<PUBLIC_IP>:8501`
  - "Please wait..."에서 멈추면 WebSocket 차단 문제 → [installation-and-run.md](./installation-and-run.md#문제-해결-대시보드가-please-wait-에서-멈출-때) 참고.
- **로그**: `journalctl -u kis-trader -f` 또는 `logs/trading.log`

---

## 6. 코드 업데이트

GitHub에 새 커밋이 올라오면 VM에서 아래로 갱신합니다.
```bash
cd ~/stock-quant-trader-kis
git pull
sudo systemctl restart kis-trader kis-dashboard
```

---

## 7. 체크리스트 & 주의사항

- [ ] `.env`는 VM에만 존재하고 GitHub에 커밋되지 않음(`.gitignore` 확인).
- [ ] 8501 포트는 가능하면 본인 IP만 허용(계좌·손익 노출 방지).
- [ ] Oracle Ampere 재고 부족 시 AMD Micro로 대체하거나 리전을 바꿔 재시도.
- [ ] **실계좌 전환 전 반드시 모의투자(`KIS_VIRTUAL_TRADING=true`)로 충분히 검증**.
- [ ] 무료 VM도 리소스 초과·정책 위반 시 정지될 수 있으니, 중요 데이터(`data/`)는 주기적으로 백업.

> ⚠️ 투자 손실 책임은 전적으로 사용자 본인에게 있습니다. [면책 조항](../README.md#-면책-조항-및-투자-위험-고지-disclaimer) 참고.
