# cme_monitor_app_enhanced.py - Getcmesymbols.pyの銘柄取得方法を統合
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import threading
import time
import json
import os
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

class TopstepXAPI:
    def __init__(self, username, api_key, debug=False):
        self.username = username
        self.api_key = api_key
        self.base_url = "https://api.topstepx.com/api"
        self.session_token = None
        self.debug = debug
    
    def authenticate(self):
        """認証"""
        url = f"{self.base_url}/Auth/loginKey"
        payload = {"userName": self.username, "apiKey": self.api_key}
        response = requests.post(url, json=payload)
        data = response.json()
        
        if data.get('success'):
            self.session_token = data.get('token')
            return True
        return False
    
    def search_contracts(self, search_text="", live=False, silent=False):
        """契約を検索"""
        if not self.session_token:
            return None
        
        url = f"{self.base_url}/Contract/search"
        headers = {"Authorization": f"Bearer {self.session_token}", "Content-Type": "application/json"}
        payload = {"searchText": search_text, "live": live}
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('contracts', [])
        return None
    
    def get_contracts_by_category(self, log_callback=None):
        """
        カテゴリ別に銘柄を取得（Getcmesymbols.pyから移植）
        より多くの銘柄を取得するための包括的な方法
        """
        if not self.session_token:
            if log_callback:
                log_callback("❌ 先に authenticate() を実行してください")
            return None
        
        if log_callback:
            log_callback("📊 カテゴリ別検索で銘柄を取得中...")
        
        # 主要なCME先物のプレフィックス（拡張版）
        categories = {
            '株価指数': [
                # Standard E-mini
                'ES', 'NQ', 'YM', 'RTY', 
                # International
                'NKD', 'NIY',  # Nikkei 225
                # Micro E-mini
                'MES', 'MNQ', 'M2K', 'MYM',
                # その他
                'EMD', 'SSG'
            ],
            '通貨': [
                'EC', '6E', '6J', '6B', '6C', '6A', '6S', '6N', '6M',
                'DX', 'E7', 'J7', 'AUD', 'CAD', 'CHF', 'EUR', 'GBP', 'JPY', 'NZD'
            ],
            'エネルギー': [
                'CL', 'NG', 'RB', 'HO', 'BZ', 'QG', 'QM',
                'MCL', 'MGC'  # Micro contracts
            ],
            '貴金属': [
                'GC', 'SI', 'HG', 'PL', 'PA',
                'QO', 'QI', 'MGC', 'SIL'  # Micro & E-micro
            ],
            '農産物': [
                'ZC', 'ZS', 'ZW', 'ZL', 'ZM', 'ZO', 'ZR',
                'CT', 'KC', 'SB', 'CC', 'OJ',
                'DC', 'DY'  # Dairy
            ],
            '畜産': ['LE', 'HE', 'GF', 'DC'],
            '債券': [
                'ZB', 'ZN', 'ZF', 'ZT', 'UB',
                'TWE', 'FV'  # Ultra T-Bond, Five Year
            ],
            '仮想通貨': ['BTC', 'ETH', 'MBT', 'MET'],
            'ボラティリティ': ['VX', 'VXM'],
            'その他': ['BRN', 'LBS']
        }
        
        all_contracts = {}
        total_found = 0
        
        for category, prefixes in categories.items():
            if log_callback:
                log_callback(f"  🔍 {category}カテゴリを検索中...")
            
            category_contracts = []
            
            for prefix in prefixes:
                contracts = self.search_contracts(search_text=prefix, live=False, silent=True)
                if contracts:
                    # 重複を避けるため、本当にそのプレフィックスで始まるものだけを追加
                    filtered = [c for c in contracts if c.get('name', '').startswith(prefix)]
                    category_contracts.extend(filtered)
            
            # 重複を除去（idで判定）
            unique_contracts = []
            seen_ids = set()
            for contract in category_contracts:
                contract_id = contract.get('id')
                if contract_id and contract_id not in seen_ids:
                    unique_contracts.append(contract)
                    seen_ids.add(contract_id)
            
            all_contracts[category] = unique_contracts
            total_found += len(unique_contracts)
            
            if log_callback:
                log_callback(f"    ✅ {category}: {len(unique_contracts)}件")
        
        if log_callback:
            log_callback(f"✅ カテゴリ別検索完了: 合計 {total_found}件")
        
        return all_contracts
    
    def get_all_contracts_comprehensive(self, log_callback=None):
        """
        包括的な銘柄取得（2つの方法を組み合わせ）
        Getcmesymbols.pyの手法を移植
        """
        if log_callback:
            log_callback("🔍 包括的な銘柄取得を開始...")
        
        # 方法1: 標準的な全件取得
        if log_callback:
            log_callback("  方法1: 空検索で全銘柄取得...")
        contracts_method1 = self.search_contracts(search_text="", live=False)
        
        if contracts_method1:
            if log_callback:
                log_callback(f"    ✅ {len(contracts_method1)}件取得")
        else:
            contracts_method1 = []
            if log_callback:
                log_callback("    ⚠️ 空検索では銘柄が取得できませんでした")
        
        # 方法2: カテゴリ別検索
        if log_callback:
            log_callback("  方法2: カテゴリ別検索...")
        contracts_by_category = self.get_contracts_by_category(log_callback)
        
        # カテゴリ別の契約を1つのリストにまとめる
        contracts_method2 = []
        if contracts_by_category:
            for category, contracts in contracts_by_category.items():
                contracts_method2.extend(contracts)
        
        # 両方の結果をマージ
        if log_callback:
            log_callback(f"  📊 マージ中...")
            log_callback(f"    方法1: {len(contracts_method1)}件")
            log_callback(f"    方法2: {len(contracts_method2)}件")
        
        all_contracts = self._merge_contract_lists(contracts_method1, contracts_method2)
        
        if log_callback:
            log_callback(f"✅ マージ完了: 合計 {len(all_contracts)}件の銘柄を取得")
        
        return all_contracts, contracts_by_category
    
    def _merge_contract_lists(self, list1, list2):
        """2つの契約リストをマージ（重複除去）"""
        if not list1:
            return list2 or []
        if not list2:
            return list1 or []
        
        merged = list1.copy()
        existing_ids = {c.get('id') for c in list1}
        
        for contract in list2:
            contract_id = contract.get('id')
            if contract_id and contract_id not in existing_ids:
                merged.append(contract)
                existing_ids.add(contract_id)
        
        return merged
    
    def get_historical_data(self, contract_id, timeframe="1D", limit=500):
        """履歴データを取得"""
        if not self.session_token:
            return None
        
        url = f"{self.base_url}/History/retrieveBars"
        headers = {"Authorization": f"Bearer {self.session_token}", "Content-Type": "application/json"}
        
        # 時間足に応じたunitとunitNumberの設定
        timeframe_map = {
            "3m": {"unit": 2, "unitNumber": 3, "days": 7},
            "15m": {"unit": 2, "unitNumber": 15, "days": 14},
            "1H": {"unit": 3, "unitNumber": 1, "days": 30},
            "4H": {"unit": 3, "unitNumber": 4, "days": 60},
            "1D": {"unit": 4, "unitNumber": 1, "days": 90}
        }
        
        tf_config = timeframe_map.get(timeframe, timeframe_map["1D"])
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=tf_config["days"])
        
        payload = {
            "contractId": contract_id,
            "live": False,
            "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unit": tf_config["unit"],
            "unitNumber": tf_config["unitNumber"],
            "limit": limit,
            "includePartialBar": False
        }
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json().get('data', response.json().get('bars', response.json()))
        return None


class MarketAnalyzer:
    """市場分析クラス"""
    
    @staticmethod
    def calculate_indicators(df, debug=False):
        """指標を計算"""
        df = df.copy()
        
        # カラム名の標準化
        rename_map = {
            't': 'time', 'timestamp': 'time', 'datetime': 'time', 'date': 'time',
            'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'
        }
        
        actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(columns=actual_rename)
        
        # 時刻カラムを探す
        time_col = None
        for col in ['time', 't', 'timestamp', 'datetime', 'date']:
            if col in df.columns:
                time_col = col
                break
        
        if time_col is None:
            raise ValueError(f"時刻カラムが見つかりません。カラム: {df.columns.tolist()}")
        
        if time_col != 'time':
            df = df.rename(columns={time_col: 'time'})
        
        # 並べ替え
        df = df.sort_values('time').reset_index(drop=True)
        
        # 必須カラムの存在確認
        required_cols = ['high', 'low', 'close']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"必須カラムが不足: {missing_cols}")
        
        # チャイキンボラティリティ(Length=10, ROCLength=12)
        df['hl_range'] = df['high'] - df['low']
        ema_hl = df['hl_range'].ewm(span=10, adjust=False, min_periods=10).mean()
        df['chaikin_vol'] = ((ema_hl - ema_hl.shift(12)) / ema_hl.shift(12)) * 100
        
        # ROC (Rate of Change)
        df['roc'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100
        
        return df
    
    @staticmethod
    def determine_market_state(chaikin_vol, roc):
        """市場状態を判定"""
        if pd.isna(chaikin_vol) or pd.isna(roc):
            return "データ不足", "⚪"
        
        # スクイーズ
        if chaikin_vol < -10 and abs(roc) < 2:
            return "スクイーズ(エネルギー蓄積)", "🟡"
        
        # トレンド開始
        elif chaikin_vol > 10 and abs(roc) > 3:
            direction = "上昇" if roc > 0 else "下降"
            return f"トレンド開始({direction})", "🔴"
        
        # レンジ
        else:
            return "レンジ", "🟢"


class ConfigManager:
    """設定管理クラス"""
    
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.default_config = {
            "watched_symbols": ['ESZ5', 'NQZ5', 'GCZ5', 'CLZ5'],
            "timeframe": "15m",
            "auto_update_interval": 60,
            "debug_mode": False,
            "squeeze_threshold": -10,
            "trend_threshold": 10,
            "roc_squeeze_threshold": 2,
            "roc_trend_threshold": 3
        }
    
    def load_config(self):
        """設定を読み込み"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
                return self.default_config
        return self.default_config
    
    def save_config(self, config):
        """設定を保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"設定保存エラー: {e}")
            return False


class SymbolManagerDialog:
    """銘柄管理ダイアログ（カテゴリ別表示対応）"""
    
    def __init__(self, parent, all_contracts, contracts_by_category, watched_symbols, callback):
        self.parent = parent
        self.all_contracts = all_contracts
        self.contracts_by_category = contracts_by_category or {}
        self.watched_symbols = watched_symbols.copy()
        self.callback = callback
        self.current_category = "全て"
        
        # ダイアログウィンドウを作成
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("📊 銘柄管理（カテゴリ別表示）")
        self.dialog.geometry("900x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        """UIセットアップ"""
        # タイトルフレーム
        title_frame = tk.Frame(self.dialog, bg="#2c3e50")
        title_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            title_frame,
            text="📊 監視銘柄の管理（カテゴリ別表示）",
            font=("Arial", 14, "bold"),
            bg="#2c3e50",
            fg="white"
        ).pack(pady=10)
        
        # メインフレーム(2カラム)
        main_frame = tk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左側:利用可能な銘柄
        left_frame = tk.LabelFrame(main_frame, text="利用可能な銘柄", font=("Arial", 10, "bold"))
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # カテゴリ選択フレーム
        category_frame = tk.Frame(left_frame)
        category_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(category_frame, text="📂 カテゴリ:").pack(side=tk.LEFT, padx=5)
        
        # カテゴリリスト
        categories = ["全て"] + sorted(self.contracts_by_category.keys())
        self.category_var = tk.StringVar(value="全て")
        category_combo = ttk.Combobox(
            category_frame,
            textvariable=self.category_var,
            values=categories,
            state="readonly",
            width=15
        )
        category_combo.pack(side=tk.LEFT, padx=5)
        category_combo.bind('<<ComboboxSelected>>', self.on_category_change)
        
        # 銘柄数表示
        self.available_count_label = tk.Label(left_frame, text="", font=("Arial", 9), fg="gray")
        self.available_count_label.pack(anchor=tk.W, padx=10, pady=2)
        
        # 検索フィールド
        search_frame = tk.Frame(left_frame)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(search_frame, text="🔍 検索:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_contracts)
        tk.Entry(search_frame, textvariable=self.search_var, width=20).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # クリアボタン
        tk.Button(
            search_frame,
            text="✕",
            command=lambda: self.search_var.set(""),
            bg="#e74c3c",
            fg="white",
            font=("Arial", 9, "bold"),
            width=3
        ).pack(side=tk.LEFT, padx=2)
        
        # 利用可能な銘柄リスト
        list_frame = tk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.available_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Courier", 10))
        self.available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.available_listbox.yview)
        
        # リストボックスをダブルクリックで追加
        self.available_listbox.bind('<Double-Button-1>', lambda e: self.add_symbol())
        
        # 契約情報を格納
        self.contract_map = {}
        self.populate_available_contracts()
        
        # 中央:ボタン
        button_frame = tk.Frame(main_frame, width=80)
        button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=50)
        
        tk.Button(
            button_frame,
            text="➡️\n追加",
            command=self.add_symbol,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            height=3
        ).pack(pady=10)
        
        tk.Button(
            button_frame,
            text="⬅️\n削除",
            command=self.remove_symbol,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            height=3
        ).pack(pady=10)
        
        # 右側:監視中の銘柄
        right_frame = tk.LabelFrame(main_frame, text="監視中の銘柄", font=("Arial", 10, "bold"))
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 銘柄数表示
        self.watched_count_label = tk.Label(right_frame, text="", font=("Arial", 9), fg="gray")
        self.watched_count_label.pack(anchor=tk.W, padx=10, pady=2)
        
        list_frame2 = tk.Frame(right_frame)
        list_frame2.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar2 = tk.Scrollbar(list_frame2)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.watched_listbox = tk.Listbox(list_frame2, yscrollcommand=scrollbar2.set, font=("Courier", 10))
        self.watched_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar2.config(command=self.watched_listbox.yview)
        
        # リストボックスをダブルクリックで削除
        self.watched_listbox.bind('<Double-Button-1>', lambda e: self.remove_symbol())
        
        self.populate_watched_symbols()
        
        # 下部:ボタン
        bottom_frame = tk.Frame(self.dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            bottom_frame,
            text="✅ 保存して閉じる",
            command=self.save_and_close,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold"),
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            bottom_frame,
            text="📋 カテゴリ統計",
            command=self.show_category_stats,
            bg="#9b59b6",
            fg="white",
            font=("Arial", 11, "bold"),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            bottom_frame,
            text="❌ キャンセル",
            command=self.dialog.destroy,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 11, "bold"),
            width=15
        ).pack(side=tk.RIGHT, padx=5)
    
    def on_category_change(self, event=None):
        """カテゴリ変更時の処理"""
        self.current_category = self.category_var.get()
        self.populate_available_contracts()
    
    def populate_available_contracts(self):
        """利用可能な契約をリストに表示（カテゴリフィルタ対応）"""
        self.available_listbox.delete(0, tk.END)
        self.contract_map.clear()
        
        if not self.all_contracts:
            self.available_count_label.config(text="銘柄データなし")
            return
        
        # カテゴリフィルタを適用
        if self.current_category == "全て":
            filtered_contracts = self.all_contracts
        else:
            filtered_contracts = self.contracts_by_category.get(self.current_category, [])
        
        # 既に表示した銘柄を追跡
        displayed_names = set()
        
        for contract in filtered_contracts:
            name = contract.get('name', '')
            # 監視中でない、かつまだ表示していない銘柄のみ
            if name not in self.watched_symbols and name not in displayed_names:
                description = contract.get('description', 'N/A')
                display_text = f"{name:10s} - {description}"
                self.available_listbox.insert(tk.END, display_text)
                self.contract_map[display_text] = contract
                displayed_names.add(name)
        
        # 銘柄数を表示
        total_available = len(self.contract_map)
        total_all = len(filtered_contracts)
        category_text = f"[{self.current_category}]" if self.current_category != "全て" else ""
        self.available_count_label.config(text=f"利用可能: {total_available}銘柄 {category_text}")
    
    def filter_contracts(self, *args):
        """検索フィルタを適用"""
        search_text = self.search_var.get().upper()
        self.available_listbox.delete(0, tk.END)
        
        for display_text, contract in self.contract_map.items():
            if search_text in display_text.upper():
                self.available_listbox.insert(tk.END, display_text)
    
    def populate_watched_symbols(self):
        """監視中の銘柄をリストに表示"""
        self.watched_listbox.delete(0, tk.END)
        
        for symbol in self.watched_symbols:
            # 説明を追加
            description = "N/A"
            for contract in self.all_contracts:
                if contract.get('name', '') == symbol:
                    description = contract.get('description', 'N/A')
                    break
            
            display_text = f"{symbol:10s} - {description}"
            self.watched_listbox.insert(tk.END, display_text)
        
        # 銘柄数を表示
        self.watched_count_label.config(text=f"監視中: {len(self.watched_symbols)}銘柄")
    
    def add_symbol(self):
        """銘柄を追加"""
        selection = self.available_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "追加する銘柄を選択してください")
            return
        
        selected_text = self.available_listbox.get(selection[0])
        contract = self.contract_map.get(selected_text)
        
        if contract:
            symbol = contract.get('name', '')
            if symbol and symbol not in self.watched_symbols:
                self.watched_symbols.append(symbol)
                self.populate_available_contracts()
                self.populate_watched_symbols()
    
    def remove_symbol(self):
        """銘柄を削除"""
        selection = self.watched_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "削除する銘柄を選択してください")
            return
        
        selected_text = self.watched_listbox.get(selection[0])
        symbol = selected_text.split()[0]  # 最初のワード(銘柄コード)を取得
        
        if symbol in self.watched_symbols:
            if len(self.watched_symbols) <= 1:
                messagebox.showwarning("警告", "最低1つの銘柄を監視する必要があります")
                return
            
            self.watched_symbols.remove(symbol)
            self.populate_available_contracts()
            self.populate_watched_symbols()
    
    def show_category_stats(self):
        """カテゴリ統計を表示"""
        stats_window = tk.Toplevel(self.dialog)
        stats_window.title("📊 カテゴリ統計")
        stats_window.geometry("600x500")
        
        # テキストエリア
        text_frame = tk.Frame(stats_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, yscrollcommand=scrollbar.set, font=("Courier", 10))
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # 統計情報を表示
        text_widget.insert(tk.END, f"=== カテゴリ別統計 ===\n\n")
        text_widget.insert(tk.END, f"全契約数: {len(self.all_contracts)}\n")
        text_widget.insert(tk.END, f"監視中: {len(self.watched_symbols)}銘柄\n\n")
        
        text_widget.insert(tk.END, f"{'カテゴリ':<20} {'銘柄数':>10} {'監視中':>10}\n")
        text_widget.insert(tk.END, "=" * 50 + "\n")
        
        # カテゴリ別統計
        for category in sorted(self.contracts_by_category.keys()):
            contracts = self.contracts_by_category[category]
            total = len(contracts)
            watched = sum(1 for c in contracts if c.get('name') in self.watched_symbols)
            
            text_widget.insert(tk.END, f"{category:<20} {total:>10} {watched:>10}\n")
        
        text_widget.config(state=tk.DISABLED)
        
        # 閉じるボタン
        tk.Button(
            stats_window,
            text="閉じる",
            command=stats_window.destroy,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold")
        ).pack(pady=10)
    
    def save_and_close(self):
        """保存して閉じる"""
        if len(self.watched_symbols) == 0:
            messagebox.showwarning("警告", "最低1つの銘柄を選択してください")
            return
        
        self.callback(self.watched_symbols)
        self.dialog.destroy()


class CMEMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CME先物監視アプリ v6.0 - 包括的銘柄取得対応")
        self.root.geometry("1100x750")
        
        # 設定管理
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        
        # 環境変数からAPI認証情報を取得
        self.username = os.getenv('TOPSTEPX_USERNAME')
        self.api_key = os.getenv('TOPSTEPX_API_KEY')
        
        # 認証情報の確認
        if not self.username or not self.api_key:
            messagebox.showerror(
                "環境変数エラー",
                "TopstepX APIの認証情報が設定されていません。\n\n"
                ".envファイルに以下を設定してください:\n"
                "TOPSTEPX_USERNAME=your_username\n"
                "TOPSTEPX_API_KEY=your_api_key\n\n"
                "詳細はREADME.mdを参照してください。"
            )
            self.root.quit()
            return
        
        self.api = None
        
        # 監視銘柄
        self.watched_symbols = self.config.get('watched_symbols', ['ESZ5', 'NQZ5', 'GCZ5', 'CLZ5'])
        self.timeframe = self.config.get('timeframe', '15m')
        self.debug_mode = self.config.get('debug_mode', False)
        self.contracts = {}
        self.all_contracts = []
        self.contracts_by_category = {}
        
        # 自動更新スレッド
        self.auto_update_running = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """UI構築"""
        # トップフレーム:ステータス
        top_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = tk.Label(
            top_frame, 
            text="🔴 未接続", 
            font=("Arial", 14, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        self.status_label.pack(pady=15)
        
        # 時間足選択フレーム
        timeframe_frame = tk.Frame(self.root, bg="#34495e")
        timeframe_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            timeframe_frame,
            text="⏱️ 時間足:",
            font=("Arial", 11, "bold"),
            bg="#34495e",
            fg="white"
        ).pack(side=tk.LEFT, padx=10)
        
        # 時間足選択ラジオボタン
        self.timeframe_var = tk.StringVar(value=self.timeframe)
        timeframe_options = [
            ("3分足", "3m"),
            ("15分足", "15m"),
            ("1時間足", "1H"),
            ("4時間足", "4H"),
            ("日足", "1D")
        ]
        
        for label, value in timeframe_options:
            tk.Radiobutton(
                timeframe_frame,
                text=label,
                variable=self.timeframe_var,
                value=value,
                font=("Arial", 10),
                bg="#34495e",
                fg="white",
                selectcolor="#2c3e50",
                command=self.on_timeframe_change
            ).pack(side=tk.LEFT, padx=5)
        
        # デバッグモード切り替え
        self.debug_var = tk.BooleanVar(value=self.debug_mode)
        tk.Checkbutton(
            timeframe_frame,
            text="🛠 デバッグモード",
            variable=self.debug_var,
            font=("Arial", 10),
            bg="#34495e",
            fg="white",
            selectcolor="#2c3e50",
            command=self.toggle_debug_mode
        ).pack(side=tk.RIGHT, padx=10)
        
        # ボタンフレーム
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(
            button_frame,
            text="🔌 接続",
            command=self.connect,
            bg="#27ae60",
            fg="white",
            font=("Arial", 11, "bold"),
            width=10
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="📊 銘柄管理",
            command=self.open_symbol_manager,
            bg="#9b59b6",
            fg="white",
            font=("Arial", 11, "bold"),
            width=12
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="🔄 更新",
            command=self.update_data,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold"),
            width=10
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="⏰ 自動更新開始",
            command=self.start_auto_update,
            bg="#f39c12",
            fg="white",
            font=("Arial", 11, "bold"),
            width=13
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="⏸️ 自動更新停止",
            command=self.stop_auto_update,
            bg="#e67e22",
            fg="white",
            font=("Arial", 11, "bold"),
            width=13
        ).pack(side=tk.LEFT, padx=3)
        
        # 結果表示用テーブル
        table_frame = tk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Treeview(テーブル)
        columns = ("銘柄", "時間足", "状態", "終値", "チャイキンVol", "ROC", "データ時刻", "更新時刻")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        
        for col in columns:
            self.tree.heading(col, text=col)
            if col == "銘柄":
                self.tree.column(col, width=100, anchor=tk.CENTER)
            elif col == "時間足":
                self.tree.column(col, width=80, anchor=tk.CENTER)
            elif col in ["データ時刻", "更新時刻"]:
                self.tree.column(col, width=140, anchor=tk.CENTER)
            else:
                self.tree.column(col, width=130, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # ログ表示
        log_frame = tk.LabelFrame(self.root, text="📋 ログ", font=("Arial", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Courier", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 初期ログ
        self.log(f"監視銘柄: {', '.join(self.watched_symbols)}")
        self.log(f"時間足: {self.get_timeframe_label(self.timeframe)}")
        self.log(f"デバッグモード: {'ON' if self.debug_mode else 'OFF'}")
        self.log("「接続」ボタンをクリックしてAPIに接続してください")
        
    def get_timeframe_label(self, tf):
        """時間足コードからラベルに変換"""
        tf_map = {
            "3m": "3分足",
            "15m": "15分足",
            "1H": "1時間足",
            "4H": "4時間足",
            "1D": "日足"
        }
        return tf_map.get(tf, tf)
    
    def toggle_debug_mode(self):
        """デバッグモード切り替え"""
        self.debug_mode = self.debug_var.get()
        self.config['debug_mode'] = self.debug_mode
        self.config_manager.save_config(self.config)
        self.log(f"🛠 デバッグモード: {'ON' if self.debug_mode else 'OFF'}")
    
    def on_timeframe_change(self):
        """時間足変更時の処理"""
        self.timeframe = self.timeframe_var.get()
        self.log(f"⏱️ 時間足を変更: {self.get_timeframe_label(self.timeframe)}")
        
        # 設定を保存
        self.config['timeframe'] = self.timeframe
        self.config_manager.save_config(self.config)
        
        # データを更新
        if self.api and self.contracts:
            self.update_data()
    
    def open_symbol_manager(self):
        """銘柄管理ダイアログを開く"""
        if not self.api or not self.all_contracts:
            messagebox.showwarning("警告", "先にAPIに接続してください")
            return
        
        SymbolManagerDialog(
            self.root, 
            self.all_contracts, 
            self.contracts_by_category,
            self.watched_symbols, 
            self.on_symbols_updated
        )
    
    def on_symbols_updated(self, new_symbols):
        """銘柄が更新された時の処理"""
        self.watched_symbols = new_symbols
        self.config['watched_symbols'] = self.watched_symbols
        self.config_manager.save_config(self.config)
        
        self.log(f"✅ 監視銘柄を更新: {', '.join(self.watched_symbols)}")
        
        # 契約情報を更新
        self.contracts.clear()
        for symbol_prefix in self.watched_symbols:
            for contract in self.all_contracts:
                if contract.get('name', '') == symbol_prefix:
                    self.contracts[symbol_prefix] = contract
                    break
        
        # データを更新
        self.update_data()
    
    def log(self, message):
        """ログ出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def connect(self):
        """API接続（包括的な銘柄取得）"""
        self.log("TopstepX APIに接続中...")
        self.log("📊 Getcmesymbols.pyの手法で包括的に銘柄を取得します")
        self.status_label.config(text="🟡 接続中...")
        
        def connect_thread():
            self.api = TopstepXAPI(self.username, self.api_key, debug=self.debug_mode)
            
            if self.api.authenticate():
                self.log("✅ 認証成功")
                self.status_label.config(text="🟢 接続済み")
                
                # 包括的な銘柄取得（Getcmesymbols.pyの手法）
                self.all_contracts, self.contracts_by_category = self.api.get_all_contracts_comprehensive(
                    log_callback=self.log
                )
                
                if self.all_contracts:
                    self.log(f"🎉 合計 {len(self.all_contracts)}件の銘柄を取得しました")
                    
                    # カテゴリ統計を表示
                    if self.contracts_by_category:
                        self.log("\n📊 カテゴリ別統計:")
                        for category in sorted(self.contracts_by_category.keys()):
                            count = len(self.contracts_by_category[category])
                            self.log(f"  • {category}: {count}件")
                    
                    # 監視銘柄の契約を取得
                    self.log("\n🔍 監視銘柄の契約を取得中...")
                    for symbol_prefix in self.watched_symbols:
                        for contract in self.all_contracts:
                            if contract.get('name', '') == symbol_prefix:
                                self.contracts[symbol_prefix] = contract
                                self.log(f"  ✅ {symbol_prefix}: {contract.get('description')}")
                                break
                    
                    self.log(f"\n✅ 監視銘柄数: {len(self.contracts)}件")
                    
                    # 見つからなかった銘柄を報告
                    not_found = [s for s in self.watched_symbols if s not in self.contracts]
                    if not_found:
                        self.log(f"⚠️ 以下の銘柄が見つかりませんでした: {', '.join(not_found)}")
                else:
                    self.log("❌ 銘柄情報の取得に失敗")
            else:
                self.log("❌ 認証失敗")
                self.status_label.config(text="🔴 接続失敗")
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def update_data(self):
        """データ更新"""
        if not self.api or not self.contracts:
            self.log("⚠️ 先に接続してください")
            return
        
        self.log(f"データ更新中... ({self.get_timeframe_label(self.timeframe)})")
        
        def update_thread():
            # テーブルをクリア
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            for symbol, contract in self.contracts.items():
                contract_id = contract.get('id')
                name = contract.get('name')
                
                self.log(f"📊 {name} のデータ取得中... ({self.get_timeframe_label(self.timeframe)})")
                
                # データ取得(選択された時間足)
                bars = self.api.get_historical_data(contract_id, timeframe=self.timeframe, limit=500)
                
                if not bars or len(bars) == 0:
                    self.log(f"❌ {name}: データ取得失敗")
                    continue
                
                # DataFrameに変換
                df = pd.DataFrame(bars)
                df = MarketAnalyzer.calculate_indicators(df, debug=self.debug_mode)
                
                # 最新データ
                latest = df.iloc[-1]
                chaikin_vol = latest.get('chaikin_vol', 0)
                roc = latest.get('roc', 0)
                close = latest.get('close', 0)
                data_time = latest.get('time', 'N/A')
                
                # 市場状態判定
                state, emoji = MarketAnalyzer.determine_market_state(chaikin_vol, roc)
                
                # データ時刻をフォーマット
                try:
                    from datetime import datetime as dt
                    data_time_str = dt.fromisoformat(data_time.replace('Z', '+00:00')).strftime("%m/%d %H:%M")
                except:
                    data_time_str = str(data_time)[:16] if len(str(data_time)) > 16 else str(data_time)
                
                # テーブルに追加
                self.tree.insert("", tk.END, values=(
                    f"{emoji} {name}",
                    self.get_timeframe_label(self.timeframe),
                    state,
                    f"${close:.2f}",
                    f"{chaikin_vol:.2f}%" if not pd.isna(chaikin_vol) else "N/A",
                    f"{roc:.2f}%" if not pd.isna(roc) else "N/A",
                    data_time_str,
                    datetime.now().strftime("%H:%M:%S")
                ))
                
                self.log(f"✅ {name}: {state} (CV: {chaikin_vol:.2f}%)")
            
            self.log("🎉 更新完了")
        
        threading.Thread(target=update_thread, daemon=True).start()
    
    def start_auto_update(self):
        """自動更新開始"""
        if self.auto_update_running:
            self.log("⚠️ 自動更新は既に実行中です")
            return
        
        self.auto_update_running = True
        interval = self.config.get('auto_update_interval', 60)
        self.log(f"⏰ 自動更新を開始({interval}秒ごと)")
        
        def auto_update_loop():
            while self.auto_update_running:
                self.update_data()
                time.sleep(interval)
        
        threading.Thread(target=auto_update_loop, daemon=True).start()
    
    def stop_auto_update(self):
        """自動更新停止"""
        if not self.auto_update_running:
            self.log("⚠️ 自動更新は実行されていません")
            return
        
        self.auto_update_running = False
        self.log("⏸️ 自動更新を停止しました")


if __name__ == "__main__":
    root = tk.Tk()
    app = CMEMonitorApp(root)
    root.mainloop()
