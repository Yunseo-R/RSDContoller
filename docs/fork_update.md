# Forked repository update

Fork한 원본 repository(Upstream)에 변경 사항이 생겼을 때, 
로컬 repository를 최신 상태로 업데이트하는 방법


## 1. Upstream(원본) 저장소 등록

로컬 저장소에 원본 저장소(Upstream)를 remote로 추가 (한 번만 진행)

> git remote add upstream <원본 저장소 url>

example:
```shell
git remote add upstream https://bitbucket.org/huintech-2023/rsdcontoller.git
```

- `upstream`은 관례적으로 원본 저장소에 붙이는 이름임


## 2. Upstream의 변경 사항 가져오기
- 원본 저장소의 최신 커밋과 브랜치 정보를 가져옴

```shell
git fetch upstream
```

## 3. 로컬 브랜치로 이동
- local branch: `develop`

```shell
git checkout develop
```

## 4. 로컬 브랜치에 Upstream 변경 사항 병합

### (1) merge 방식
- 충돌이 적고, 커밋 이력을 모두 남김

develop 브랜치를 업데이트:
```shell
git merge upstream/develop
```
---

#### merge error (1)
```shell
error: Your local changes to the following files would be overwritten by merge:
 file1
 file2
 ...
Please commit your changes or stash them before you merge.
Aborting.
```

로컬에서 수정한 파일이 있는데, merge를 하면 이 파일들이 덮어써질 수 있으니 먼저 정리하라는 메시지.

##### 해결 방법

(a) **변경사항 커밋:**

- 변경된 파일 커밋
```shell
git add .
git commit -m "작업 중인 변경사항 커밋"
```

- merge 시도
```shell
git merge upstream/develop
```

(b) **변경사항 임시저장 (stash):**

- 변경사항 임시 저장
```shell
git stash
```

- merge 시도
```shell
git merge upstream/develop
```

- 임시 저장한 변경사항 복원
```shell
git stash pop
```
- **충돌 발생시, 직접 해결**

(c) **변경사항을 버릴 경우 (reset):**

- 필요없는 변경사항 일 경우
- **이 명령은 모든 미커밋 변경사항을 삭제함**
```shell
git reset --hard
```

---

#### merge error (2)
```shell
fatal: refusing to merge unrelated histories
```

**로컬 브랜치와 upstream 브랜치의 커밋 히스토리가 완전히 달라서** git이 자동으로 병합을 거부할 때 발생  


주로 다음과 같은 경우에 발생:

- 로컬에서 새로 git init 후 원본을 추가한 경우

- fork 후 커밋 히스토리가 완전히 달라진 경우


##### 해결 방법

(a) `--allow-unrelated-histories` 옵션 사용

- 강제로 병합하려면 아래처럼 옵션을 추가:
```shell
git merge upstream/develop --allow-unrelated-histories
```

(b) 병합이 아닌, **Upstream의 최신 내용으로 내 브랜치를 덮어쓰고 싶다면**  
    (내 변경사항이 필요 없거나, 새로 시작하고 싶을 때)

```shell
git fetch upstream
git checkout develop
git reset --hard upstream/develop
git push -f origin develop
```
**주의:** 내 develop 브랜치의 변경사항이 모두 사라짐

충돌(conflict)이 발생할 수 있으니, 충돌 파일을 직접 수정한 뒤
```shell
git add <수정한 파일>
git commit

# (optional)
git push origin develop 
```
---

### (2) rebase 방식
- 커밋 이력을 깔끔하게 정리
- 충돌시 직접 해결 필요

```shell
git rebase upstream/develop
```

## 5. 원격 저장소(origin)에 푸시

```bash
git push origin develop
```

