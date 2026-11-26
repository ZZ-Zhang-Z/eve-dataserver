# app.py
# Flask 入口（薄入口）：应用装配见 webapp/ 包，启动方式仍为 `python app.py`（监听 0.0.0.0:5000）。

from webapp import create_app

app = create_app()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)