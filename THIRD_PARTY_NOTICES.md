# Компоненты сторонних разработчиков

В EXE входят Python 3.12 (PSF License), pywebview 6.2.1 (BSD-3-Clause), PySide6 и Qt 6.8.3 (LGPL-3.0/GPL и лицензии компонентов), QtPy (MIT), openpyxl (MIT), MCP Python SDK (MIT) и зависимости. PyInstaller использует GPL с исключением для создаваемых исполняемых файлов.

Qt WebEngine содержит Chromium и компоненты с отдельными лицензиями. Официальные сведения:

- https://docs.python.org/3/license.html
- https://github.com/r0x0r/pywebview/blob/master/LICENSE
- https://doc.qt.io/qt-6/licensing.html
- https://doc.qt.io/qt-6/qtwebengine-licensing.html
- https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=6.8.3
- https://code.qt.io/cgit/qt/qtwebengine.git/tree/?h=v6.8.3
- https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/LICENSE
- https://pyinstaller.org/en/stable/license.html

Qt остаётся динамической библиотекой. Исходный код приложения и сценарий сборки доступны для воспроизведения и замены библиотек. Для отладки изменений этих библиотек обратная разработка не ограничивается приложением. Их исходный код для версии 6.8.3 доступен у Qt: [PySide6](https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=6.8.3), [Qt Base](https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.8.3), [Qt WebEngine](https://code.qt.io/cgit/qt/qtwebengine.git/tree/?h=v6.8.3). Приложение не модифицирует эти библиотеки.

Лицензионные файлы установленного набора включены в каталог `licenses/`, в том числе PSF, LGPL-3.0 и GPL. Уведомления о сторонних компонентах Qt WebEngine и ссылки на их лицензии опубликованы в [документации Qt 6.8](https://doc.qt.io/qt-6.8/qtwebengine-licensing.html).
