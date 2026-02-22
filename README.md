# famista

RetroArch の UDP メモリ読み取り（`READ_CORE_MEMORY`）を使って、
ファミスタGBの試合状態を取得・表示・記録するための検証用スクリプト集です。

- スコア、B/S/O、回（表/裏）、塁状況を取得
- OBS 用の HTML オーバーレイをローカル配信
- 学習/検証用に WRAM スナップショットを保存

## 前提条件

- Python 3.10 以上（標準ライブラリのみ。追加 pip 依存なし）
- RetroArch が `127.0.0.1:55355/UDP` でコマンド受信できること
- 対象ゲーム（ファミスタGB）実行中で、メモリアドレスがこのリポジトリの想定と一致すること

補足:
- `scoregetter.py` は `msvcrt` を使うため Windows 前提です。
- ほかのスクリプトは標準的な Python + UDP ソケットで動きます。

## クイックスタート（オーバーレイ表示）

1. RetroArch 側を起動し、対象ゲームを実行する。
2. このフォルダで以下を実行する。

```powershell
python overlay.py
```

3. ブラウザ（または OBS の Browser Source）で次を開く。

- `http://127.0.0.1:8000/overlay.html`

API:
- `http://127.0.0.1:8000/state.json`

## 主なスクリプト

| ファイル | 役割 | 出力 |
|---|---|---|
| `overlay.py` | UDP で状態を収集し、HTTP で `overlay.html` と `state.json` を配信 | `http://127.0.0.1:8000/` |
| `overlay.html` | スコアボード UI（スコア、回、B/S/O、塁、打席側） | ブラウザ表示 |
| `getallstatus.py` | 投球可能ゲートの立ち上がり時に、B/S/O + 回 + 塁 + スコアをまとめて表示 | コンソール |
| `scoreviewer.py` | 投球可能ゲートの立ち上がり時にスコアのみ表示 | コンソール |
| `getbso.py` | B/S/O と回をポーリング表示 | コンソール |
| `getbassstatus.py` | C0D3 の立ち上がりで B/S/O + 塁を更新表示 | コンソール |
| `scoregetter.py` | キー入力でスコアラベルを付けつつ、次の投球可能タイミングで WRAM を保存 | `score_snaps/*.bin`, `score_snaps/meta.csv` |
| `memchenge.py` | 指定アドレス範囲の差分監視（どのバイトが変化したか調査） | コンソール |

## `scoregetter.py` の使い方

```powershell
python scoregetter.py
```

キー操作:
- `h`: HOME +1
- `a`: AWAY +1
- `u`: 直前の変更を取り消し
- `s`: スコア変更なしで次の投球可能タイミングに保存
- `q`: 終了

保存先:
- バイナリ: `score_snaps/YYYYmmdd_HHMMSS_H{home}_A{away}.bin`
- メタ情報: `score_snaps/meta.csv`

`meta.csv` の列:
- `ts,file,home,away,note`

## ディレクトリ構成

```text
famista/
  overlay.py
  overlay.html
  scoregetter.py
  getallstatus.py
  scoreviewer.py
  getbso.py
  getbassstatus.py
  memchenge.py
  score_snaps/        # 現行スナップショット
  old/                # 過去の検証スクリプト/データ
```

## 主要メモリアドレス（現行スクリプトで使用）

| 用途 | アドレス |
|---|---|
| 投球可能ゲート1 | `0xC0D3`（P: `00` / F: `01`） |
| 投球可能ゲート2 | `0xC0CE`（P: `14` / F: `1A`） |
| Ball | `0xC0C0` |
| Strike | `0xC0C2` |
| Out | `0xC0C3` |
| Half（回の進行） | `0xC0C4` |
| 1塁 | `0xD262` |
| 2塁 | `0xD282` |
| 3塁 | `0xD2A2` |
| HOME スコア | `0xD81F` |
| AWAY スコア | `0xD83F` |

補足:
- 多くのスクリプトは「`F -> P` の立ち上がり（投球可能遷移）」を確定タイミングとして読み取ります。
- `COMMIT_DELAY_SEC` や `stable_read_u8()` は読み取りブレの吸収用です。

## `old/` ディレクトリについて

`old/` は探索・検証の過去資産です。

- 候補アドレス探索（塁判定など）の試作コード
- 旧フォーマットのスナップショット
- 解析用 CSV

通常運用はルート直下のスクリプト（特に `overlay.py`, `scoregetter.py`, `getallstatus.py`）を使ってください。

## トラブルシュート

- `read failed` が頻発する
  - RetroArch 側の UDP コマンド受信設定とポート (`55355`) を確認
  - 対象コア/ゲームが想定と異なるとアドレスが一致しない可能性あり
- 表示がズレる/不安定
  - `COMMIT_DELAY_SEC` を `0.20`〜`0.25` に上げる
  - `stable_read_u8()` のサンプル数を増やす
- 文字化けして見える
  - ターミナルや CSV ビューアの文字コードを UTF-8 に合わせる

## 注意

このリポジトリは特定環境向けのメモリマップ前提で作られています。
コアや ROM 差分でアドレス仕様が変わる場合は、各スクリプト先頭の定数を調整してください。
