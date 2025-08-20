#!/bin/bash
# 에러 발생 시 스크립트 중단
set -e
# =========================================================
# 0. 필수 도구 설치 확인 및 설치
# =========================================================
# 0-1. Azure CLI 설치 확인
echo "Azure CLI 설치 상태를 확인합니다..."
if ! command -v az &> /dev/null
then
    echo "Azure CLI가 설치되어 있지 않습니다. 설치를 시작합니다..."
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    echo "Azure CLI 설치가 완료되었습니다."
else
    echo "Azure CLI가 이미 설치되어 있습니다."
fi
# 0-2. Azure Functions Core Tools 설치 확인
echo "Azure Functions Core Tools 설치 상태를 확인합니다..."
if ! command -v func &> /dev/null
then
    echo "Azure Functions Core Tools가 설치되어 있지 않습니다. 설치를 시작합니다..."
    # Microsoft GPG 키와 apt 리포지토리 추가
    curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg
    sudo mv microsoft.gpg /etc/apt/trusted.gpg.d/microsoft.gpg
    sudo sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/repos/microsoft-ubuntu-$(lsb_release -cs 2>/dev/null)-prod $(lsb_release -cs 2>/dev/null) main" > /etc/apt/sources.list.d/dotnetdev.list'
    sudo apt-get update
    sudo apt-get install azure-functions-core-tools-4 -y
    echo "Azure Functions Core Tools 설치가 완료되었습니다."
else
    echo "Azure Functions Core Tools가 이미 설치되어 있습니다."
fi

# Azure 클라이언트 ID 설정
# dev-mid-rb-krc "40ae523e-f478-4202-ab5c-59f9e27e8104"
# "2dd53780-e036-40dc-b593-5259a87dc58e"
# prd-mid-rb-krc "60afe682-db04-4fa1-91ec-e97689d28885"
# "0317a9b6-6776-4bb9-8304-36ed52e8833d"
# prd-mid-rb-uks "4c8606c7-9186-4896-aa29-8f14824e06c8"
# "86d653bb-7d60-4095-8f60-c85b05297c7c"

CLIENT_ID="40ae523e-f478-4202-ab5c-59f9e27e8104"
SUBSCRIPTION_ID="2dd53780-e036-40dc-b593-5259a87dc58e"
# 기본값 설정
SYSTEM_NAME=""
BRANCH_NAME="release"
DEPLOYMENT_TARGETS=()
# =========================================================
# 1. 명령줄 옵션 파싱
# =========================================================
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --system-name)
            SYSTEM_NAME="$2"
            shift
            ;;
        --branch)
            BRANCH_NAME="$2"
            shift
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            echo "사용법: $0 [--system-name <시스템명>] [--branch <브랜치명>]"
            exit 1
            ;;
    esac
    shift
done
# =========================================================
# 2. 시스템별 배포할 함수 앱 이름 정의
# =========================================================
# 각 시스템별로 배포할 함수 앱 이름들을 공백으로 구분하여 정의합니다.
declare -A SYSTEM_APP_NAMES
SYSTEM_APP_NAMES=(
    ["integration"]="dev-fn-rb-krc-integration-kr dev-fn-rb-krc-integration-uk"
    ["media-kr"]="dev-fn-rb-krc-media-kr"
    ["media-uk"]="dev-fn-rb-krc-media-uk"
    ["promotion-kr"]="dev-fn-rb-krc-promotion-kr"
    ["promotion-uk"]="dev-fn-rb-krc-promotion-uk"
    ["youtube"]="dev-fn-rb-krc-youtube-kr dev-fn-rb-krc-youtube-uk"
)
# =========================================================
# 3. 배포 대상 설정
# =========================================================
if [ -n "$SYSTEM_NAME" ]; then
    # 특정 시스템이 지정된 경우, 해당 시스템의 앱만 배포
    if [[ -v SYSTEM_APP_NAMES["$SYSTEM_NAME"] ]]; then
        DEPLOYMENT_TARGETS+=("$SYSTEM_NAME")
    else
        echo "오류: '$SYSTEM_NAME' 시스템은 배포 앱이 정의되지 않았습니다."
        exit 1
    fi
else
    # 시스템명이 지정되지 않은 경우, SYSTEM_APP_NAMES에 정의된 모든 시스템 배포
    echo "시스템명이 지정되지 않았습니다. 모든 정의된 시스템을 배포합니다."
    for key in "${!SYSTEM_APP_NAMES[@]}"; do
        DEPLOYMENT_TARGETS+=("$key")
    done
fi
# =========================================================
# 4. 배포 함수 정의 및 실행
# =========================================================
deploy_function() {
    local system_name=$1
    local app_name=$2
    echo "====================================================="
    echo ">> 시스템: $system_name"
    echo ">> 함수 앱: $app_name"
    echo ">> 브랜치: $BRANCH_NAME"
    echo "-----------------------------------------------------"
    if [ ! -d "$system_name" ]; then
        echo "오류: $system_name 디렉토리가 존재하지 않습니다. 건너뜁니다."
        return
    fi
    cd "$system_name"
    git checkout "$BRANCH_NAME"
    echo "$BRANCH_NAME 브랜치로 전환 완료."
    echo "Azure Managed Identity로 로그인합니다..."
    az login --identity --client-id "$CLIENT_ID"
    az account set --subscription "$SUBSCRIPTION_ID"
    echo "$app_name 함수 앱에 배포를 시작합니다..."
    func azure functionapp publish "$app_name"
    echo "배포 명령을 실행했습니다."
    cd ..
    echo "-----------------------------------------------------"
}
# =========================================================
# 5. 배포 함수 호출
# =========================================================
if [ ${#DEPLOYMENT_TARGETS[@]} -eq 0 ]; then
    echo "배포할 대상이 없습니다. 스크립트를 종료합니다."
    exit 1
fi
for target_system in "${DEPLOYMENT_TARGETS[@]}"; do
    app_names_to_deploy=${SYSTEM_APP_NAMES[$target_system]}
    for app_name in $app_names_to_deploy; do
        deploy_function "$target_system" "$app_name"
    done
done
echo "====================================================="
echo "모든 배포 스크립트 실행 완료!"
echo "배포 완료 여부는 Azure 포털에서 확인하세요."