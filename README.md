# IoT Bridge

## 概要
IoT Bridgeは、クラウド上にデプロイされたフロントエンドアプリケーションと自宅内のIoTデバイスとの通信を橋渡しするために開発したブリッジソフトウェアです。

## システム要件
- Python 3.8以上
- pip（Pythonパッケージマネージャー）

## インストール方法

```bash
# リポジトリのクローン
git clone https://github.com/fujiwaradaikidesu/iot-bridge.git
cd iot-bridge

# 仮想環境の作成と有効化
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

## 基本的な使い方

```bash
# 設定ファイルを指定して起動
python main.py --config config/default.yml

# デバッグモードで起動
python main.py --debug

# バックグラウンドで実行
python main.py --daemon
```

## 設定

### 基本設定（config/default.yml）
```yaml
bridge:
  name: "iot-bridge"
  host: "0.0.0.0"
  port: 8080

protocols:
  mqtt:
    enabled: true
    broker: "localhost"
    port: 1883
    
  http:
    enabled: true
    port: 8081

logging:
  level: "INFO"
  file: "logs/iot-bridge.log"
```

## プロジェクト構成
```
iot-bridge/
├── src/                # ソースコード
│   ├── protocols/      # プロトコル実装
│   ├── handlers/       # イベントハンドラー
│   └── utils/         # ユーティリティ関数
├── config/            # 設定ファイル
├── tests/            # テストコード
├── docs/             # ドキュメント
└── requirements.txt  # 依存パッケージ一覧
```

## API リファレンス

### HTTP API エンドポイント
- `GET /status` - ブリッジの状態を取得
- `POST /device/register` - 新しいデバイスを登録
- `GET /devices` - 登録済みデバイス一覧を取得

### MQTT トピック
- `iot-bridge/status` - ステータス通知
- `iot-bridge/devices/#` - デバイスイベント
- `iot-bridge/control/#` - デバイス制御


## お問い合わせ
- バグ報告やご要望: [GitHub Issues](https://github.com/fujiwaradaikidesu/iot-bridge/issues)
- メンテナー: [@fujiwaradaikidesu](https://github.com/fujiwaradaikidesu)
