# 🛠️ 설치 및 실행 가이드 (User Manual)

컴퓨터에 익숙하지 않은 초보자분들도 차근차근 따라 하면 설치할 수 있도록 구성하였습니다.

> ☁️ 개인 PC/서버 대신 **무료 클라우드 VM에서 24시간 운영**하려면 [free-oracle-cloud-vm.md](./free-oracle-cloud-vm.md)를 참고하세요.

---

## 시스템 요구 사양 (System Requirements)

- **지원 운영체제**: Ubuntu 20.04+, Debian, macOS, Windows 10/11
  - *Cloud VPS(AWS, GCP, Oracle Cloud 등) Linux 환경 완벽 지원*
- **파이썬 버전**: Python 3.8 이상 (64-bit 지원)
- **네트워크**: 상시 인터넷 연결 필요

---

## 1단계: 파이썬 및 필수 패키지 설치 (Ubuntu 기준)
```bash
sudo apt update
sudo apt install python3 python3-pip git
```

## 2단계: 코드 다운로드 및 라이브러리 설치
```bash
git clone https://github.com/leemgs/stock-quant-trader-kis.git
cd stock-quant-trader-kis
pip install -r requirements.txt
```

## 3단계: 한국투자증권 API 신청
1. [한국투자증권 KIS Developers](https://apiportal.koreainvestment.com/) 접속
2. 앱 키(App Key) 및 앱 시크릿(App Secret) 발급
3. 모의투자 계좌 개설 (권장)

## 4단계: 설정 파일(.env) 세팅
보안을 위해 API 키 및 계좌 정보 등 민감한 정보는 환경 변수 파일(`.env`)에서 관리합니다.

1. `.env.sample` 파일을 복사하여 `.env` 파일을 생성합니다.
```bash
cp .env.sample .env
```
2. `.env` 파일을 열어 발급받은 키와 계좌 정보를 입력합니다.
```env
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_시크릿
KIS_ACCOUNT_NO=계좌번호8자리
```

> 📋 각 환경 변수의 상세 설명과 권장값은 [environment-variables.md](./environment-variables.md)를 참고하세요.

## 5단계: 프로그램 실행

### 옵션 A: 일반 실행 (Python)
1. 아래 명령어로 프로그램을 실행합니다.
```bash
python3 main.py
```
2. 시스템 로그와 슬랙(Slack) 알림을 통해 작동 상태를 확인합니다.

### 옵션 B: Docker Compose를 이용한 백그라운드 자동 실행 (권장)
Docker가 설치된 환경이라면 복잡한 의존성 설치 없이 아래 명령어 한 줄로 매매 봇과 실시간 대시보드를 동시에 백그라운드에서 가동할 수 있습니다.
```bash
docker-compose up -d
```
- 매매 봇 로그 실시간 확인: `docker-compose logs -f bot`
- 대시보드 접속: 브라우저에서 `http://localhost:8501` (외부 접속 시 `http://<서버_IP>:8501`)
- 시스템 전체 안전 종료: `docker-compose down`

> **참고**: 대시보드 컨테이너는 외부 IP 접속을 지원하기 위해 `--server.enableCORS=false --server.enableXsrfProtection=false` 옵션으로 실행됩니다. 자세한 내용은 아래 **문제 해결** 섹션을 참고하세요.

### 옵션 C: systemd를 이용한 부팅 시 자동 실행 (우분투)
Docker 없이 우분투 PC가 **리부팅될 때마다** 매매 봇과 대시보드가 자동으로 실행되도록 systemd 서비스로 등록하는 방법입니다. 아래 예시는 프로젝트가 `/work/github-leemgs/stock-quant-trader-kis` 폴더에 설치되어 있고, 실행 계정이 `invain`이라고 가정합니다. (본인 환경에 맞게 경로와 `User`를 수정하세요.)

**1. 매매 봇 서비스 파일 생성**

`/etc/systemd/system/kis-trader.service` 파일을 아래 내용으로 생성합니다.
```bash
sudo tee /etc/systemd/system/kis-trader.service > /dev/null << 'EOF'
[Unit]
Description=KIS Quant Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=invain
WorkingDirectory=/work/github-leemgs/stock-quant-trader-kis
ExecStart=/usr/bin/python3 /work/github-leemgs/stock-quant-trader-kis/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```
- `After=network-online.target`: 부팅 직후 네트워크가 연결된 뒤에 시작합니다. (KIS API 로그인 실패 방지)
- `Restart=on-failure`: 봇이 비정상 종료되면 10초 후 자동 재시작합니다.
- 가상환경(venv)을 사용한다면 `ExecStart`를 `/work/github-leemgs/stock-quant-trader-kis/venv/bin/python main.py` 형태로 변경하세요.

**2. 대시보드 서비스 파일 생성 (선택)**

웹 대시보드도 부팅 시 함께 띄우려면 `/etc/systemd/system/kis-dashboard.service`를 추가로 생성합니다.
```bash
sudo tee /etc/systemd/system/kis-dashboard.service > /dev/null << 'EOF'
[Unit]
Description=KIS Trading Dashboard (Streamlit)
After=network-online.target kis-trader.service
Wants=network-online.target

[Service]
Type=simple
User=invain
WorkingDirectory=/work/github-leemgs/stock-quant-trader-kis
ExecStart=/usr/bin/python3 -m streamlit run src/monitor/dashboard.py --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

**3. 서비스 등록 및 시작**
```bash
sudo systemctl daemon-reload                        # 서비스 파일 변경 사항 반영
sudo systemctl enable kis-trader kis-dashboard      # 부팅 시 자동 실행 등록
sudo systemctl start kis-trader kis-dashboard       # 지금 즉시 시작
```

**4. 운영 명령어 모음**
```bash
systemctl status kis-trader          # 현재 상태 확인
journalctl -u kis-trader -f          # 실시간 로그 확인 (Ctrl+C로 종료)
sudo systemctl restart kis-trader    # 재시작 (.env 수정 후 반영 시)
sudo systemctl stop kis-trader       # 중지
sudo systemctl disable kis-trader    # 부팅 시 자동 실행 해제
```

> **주의사항**
> - `.env` 파일은 `WorkingDirectory` 기준으로 로드되므로, 반드시 프로젝트 폴더에 `.env`가 준비된 상태에서 서비스를 시작하세요.
> - 서비스 파일을 수정한 뒤에는 항상 `sudo systemctl daemon-reload`를 먼저 실행해야 변경이 반영됩니다.
> - 실제 재부팅 후 자동 실행되는지 `sudo reboot` → `systemctl status kis-trader`로 최종 확인하는 것을 권장합니다.

### 옵션 D: systemd + Docker Compose를 이용한 부팅 시 자동 실행 (우분투)
옵션 C처럼 Python을 직접 실행하는 대신, systemd가 `docker-compose up`을 호출하여 매매 봇과 대시보드 컨테이너를 통째로 관리하는 방법입니다. 의존성 설치가 필요 없고, 봇과 대시보드가 하나의 서비스 단위로 함께 기동/종료되는 것이 장점입니다. 아래 예시는 프로젝트가 `/work/github-leemgs/stock-quant-trader-kis` 폴더에 설치되어 있다고 가정합니다. (본인 환경에 맞게 경로를 수정하세요.)

**1. 서비스 파일 생성**

`/etc/systemd/system/kis-trader-docker.service` 파일을 아래 내용으로 생성합니다.
```bash
sudo tee /etc/systemd/system/kis-trader-docker.service > /dev/null << 'EOF'
[Unit]
Description=KIS Quant Trading Bot + Dashboard (Docker Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/work/github-leemgs/stock-quant-trader-kis
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
ExecReload=/usr/local/bin/docker-compose restart

[Install]
WantedBy=multi-user.target
EOF
```
- `Requires=docker.service` / `After=docker.service`: Docker 데몬이 먼저 기동된 뒤에 컨테이너를 올립니다.
- `Type=oneshot` + `RemainAfterExit=yes`: `docker-compose up -d`는 컨테이너를 띄우고 즉시 종료되는 명령이므로, 서비스가 "실행 완료 후에도 활성(active)" 상태로 유지되도록 하는 설정입니다. 실제 프로세스 관리는 Docker가 담당합니다.
- Docker Compose **v2 플러그인**(`docker compose`, 하이픈 없음)을 사용하는 환경이라면 `ExecStart`/`ExecStop`/`ExecReload`를 각각 `/usr/bin/docker compose up -d` 형태로 변경하세요. 설치된 경로는 `which docker-compose` 또는 `docker compose version`으로 확인할 수 있습니다.

**2. 서비스 등록 및 시작**
```bash
sudo systemctl daemon-reload                  # 서비스 파일 변경 사항 반영
sudo systemctl enable kis-trader-docker      # 부팅 시 자동 실행 등록
sudo systemctl start kis-trader-docker       # 지금 즉시 시작
```

**3. 운영 명령어 모음**
```bash
systemctl status kis-trader-docker           # 서비스 상태 확인
docker-compose ps                            # 컨테이너 상태 확인 (프로젝트 폴더에서)
docker-compose logs -f bot                   # 매매 봇 실시간 로그 확인
sudo systemctl reload kis-trader-docker      # 컨테이너 재시작 (.env 수정 후 반영 시)
sudo systemctl stop kis-trader-docker        # 전체 중지 (docker-compose down)
sudo systemctl disable kis-trader-docker     # 부팅 시 자동 실행 해제
```

> **주의사항**
> - **옵션 C와 동시에 사용하지 마세요.** `kis-trader`/`kis-dashboard` 서비스(직접 Python 실행)와 이 서비스를 함께 활성화하면 매매 봇이 이중으로 실행되어 중복 주문이 발생할 수 있습니다. 하나만 `enable` 하세요.
> - `docker-compose.yml`의 `restart: unless-stopped` 정책 덕분에 Docker 데몬만 부팅 시 자동 시작되면(우분투 기본값) 컨테이너도 함께 살아납니다. 그럼에도 이 서비스를 등록해두면 `systemctl` 명령 하나로 봇 전체를 시작/중지/재시작할 수 있어 운영이 편리합니다.
> - `.env` 수정 후에는 `sudo systemctl reload kis-trader-docker`(또는 프로젝트 폴더에서 `docker-compose restart`)로 컨테이너를 재시작해야 반영됩니다.

## 6단계: 실시간 모니터링 대시보드 실행
매매 현황을 웹 브라우저에서 시각적으로 확인하려면 새 터미널을 열고 아래 명령어를 입력하세요.
```bash
streamlit run src/monitor/dashboard.py
```
*실행 후 브라우저에서 `localhost:8501` 주소로 접속하면 대시보드가 나타납니다.*

### 문제 해결: 대시보드가 "Please wait..." 에서 멈출 때
외부 IP(예: `http://<서버_IP>:8501`)로 접속했을 때 화면이 **"Please wait..."** 에서 더 진행되지 않는다면, 이는 Streamlit이 화면을 그리기 위해 맺는 **WebSocket 연결**이 차단되었기 때문입니다. (HTML/JS는 받아왔지만 WebSocket이 붙지 않아 무한 대기 상태)

1. **CORS/XSRF 보호가 원인인 경우 (대부분)**: `docker-compose.yml` 의 dashboard 커맨드에 아래 옵션이 적용되어 있는지 확인하세요. (기본 적용됨)
   ```yaml
   command: >
     streamlit run src/monitor/dashboard.py
     --server.address=0.0.0.0
     --server.enableCORS=false
     --server.enableXsrfProtection=false
   ```
   옵션 변경 후에는 컨테이너를 재생성해야 반영됩니다.
   ```bash
   docker-compose up -d --force-recreate dashboard
   ```
2. **네트워크/방화벽이 WebSocket을 차단하는 경우**: 위 옵션으로도 해결되지 않으면, 브라우저 개발자도구(F12) → Network 탭에서 `ws://<서버_IP>:8501/_stcore/stream` 연결 상태를 확인하세요. `failed`/`pending` 이라면 중간 프록시·방화벽이 WebSocket 업그레이드를 막는 것이므로, Nginx 등 리버스 프록시에서 `Upgrade`, `Connection` 헤더를 명시적으로 전달하도록 설정해야 합니다.
