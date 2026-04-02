# ToTi 배포주소
http://3.38.58.74/


# CI/CD

본 프로젝트는 GitHub Actions를 기반으로 CI(지속적 통합)와 CD(지속적 배포)를 구성하였습니다.

CI (Continuous Integration)

CI는 main, develop, feature/** 브랜치에 대한 push 및 pull_request 이벤트 시 자동 실행됩니다.
워크플로우는 Python 환경 설정 후 의존성 설치를 수행하고, ruff를 통한 코드 정적 검사, 애플리케이션 import 검증, 그리고 주요 테스트(pytest)를 실행하여 코드 품질과 안정성을 검증합니다.

CD (Continuous Deployment)

CD는 CI가 성공적으로 완료된 main 브랜치에 대해 자동 실행되며, 필요 시 수동 실행도 가능합니다.
배포 과정에서는 EC2 서버에 SSH로 접속하여 최신 코드를 반영한 후, docker compose를 이용해 기존 컨테이너를 재시작하고 최신 이미지로 서비스를 재배포합니다.

Deployment Architecture

서비스는 Docker Compose 기반으로 구성되며, 애플리케이션, 데이터베이스(PostgreSQL), 그리고 Nginx를 포함한 컨테이너 구조로 운영됩니다.
환경 변수는 .env 및 GitHub Secrets를 통해 관리되며, 민감 정보는 저장소에 포함되지 않습니다.

   * .env 필수 내용
    
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    GEMINI_API_KEY
    DATABASE_URL
    SECRET_KEY
    ACCESS_TOKEN_EXPIRE_HOURS=2


