# Pyside6

UI 구성

## pyside6 설치
```shell
pip install PySide6
```

## UI 작성
### Qt Widget Designer 실행
- windows : pyside6-designer.exe

```shell
pyside6-designer
```

## UI, resource 파일 변환 
### Convert ui (.ui) to python (.py)
> pyside6-uic [UI파일 (.ui)] -o [변환할 파일명(.py)]

example: 
- ui file : ./ui/main.ui
- conversion file : ui_main.py

```Shell
# main form 
pyside6-uic ./ui/main.ui -o ui_main.py

# config form 
pyside6-uic ./ui/config.ui -o ui_config.py
```

### convert resource (.qrc) -> python (.py)
> pyside6-rcc [resource file (.qrc)] -o [변환할 파일명(.py)]

example:
- resource file : ./resource.qrc
- conversion file : resource_rc.py

```Shell
pyside6-rcc resource.qrc -o resource_rc.py
```