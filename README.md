# RSD 모니터링 애플리케이션

PySide6 기반의 RSD 실시간 센싱 데이터 모니터링 프로그램입니다.

---

## 환경 정보

| 구성 요소     | 버전   |
|--------------|--------|
| Python       | 3.13.5 |
| PostgreSQL   | 17     |
| PySide6      | 6.4.0  |
| asyncpg      | 0.28.0 |

---

## 설정 변경
- **config.ini 수정**: 통신 간격, DB 연결 등 중앙 집중식 설정 관리 파일


## 의존성 설치
```bash
pip install -r requirements.txt
```

## 실행
```bash
python rsd_monitoring_app.py
```
