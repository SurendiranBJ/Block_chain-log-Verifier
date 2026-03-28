"""
watcher.py  —  Refactored as an importable Daemon class `LogMonitor`
"""
import hashlib
import json
import os
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from web3 import Web3
from hash_and_submit import submit_new_entries, sha256_line, CONTRACT_ADDRESS_V2, ABI_V2_PATH, RPC_URL

class TargetFileHandler(FileSystemEventHandler):
    def __init__(self, monitor):
        self.monitor = monitor
    def on_modified(self, event):
        if event.src_path == self.monitor.log_file:
            print(f"\n⚡ Watchdog: {self.monitor.log_file} modified!")
            threading.Thread(target=self.monitor.trigger_check, daemon=True).start()

class LogMonitor:
    def __init__(self, config_path):
        self.config_path   = config_path
        self.log_file      = ""
        self.case_id       = ""
        self.observer      = None
        self._check_lock   = threading.Lock()
        self.results_cache = {
            "status": "Initializing...",
            "all_ok": True,
            "file_count": 0,
            "chain_count": 0,
            "rows": []
        }
        self.node2_status = {"connected": False, "block": 0}

        self.w3       = Web3(Web3.HTTPProvider(RPC_URL))
        self.w3_node2 = Web3(Web3.HTTPProvider("http://10.80.255.234:8546"))

        if self.w3.is_connected() and os.path.exists(ABI_V2_PATH):
            with open(ABI_V2_PATH) as f:
                self.contract_v2 = self.w3.eth.contract(
                    address=CONTRACT_ADDRESS_V2, abi=json.load(f))
            self.v2_ready = True
        else:
            self.v2_ready = False

        # Start node2 status poller
        threading.Thread(target=self._poll_node2, daemon=True).start()

    def _poll_node2(self):
        while True:
            try:
                connected = self.w3_node2.is_connected()
                block     = self.w3_node2.eth.block_number if connected else 0
                self.node2_status = {"connected": connected, "block": block}
            except:
                self.node2_status = {"connected": False, "block": 0}
            time.sleep(3)

    def load_config(self):
        if not os.path.exists(self.config_path):
            return ""
        with open(self.config_path) as f:
            data = json.load(f)
            self.log_file = data.get("LOG_FILE", "")
            self.case_id  = data.get("CASE_ID", "")
        return self.log_file

    def update_target(self):
        old_file = self.log_file
        self.load_config()
        if self.log_file != old_file or not self.observer:
            print(f"🔄 LogMonitor targeting: {self.log_file}")
            self.restart_watchdog()
            threading.Thread(target=self.trigger_check, daemon=True).start()

    def restart_watchdog(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        if not self.log_file:
            return
        target_dir = os.path.dirname(self.log_file)
        if not os.path.exists(target_dir):
            return
        self.observer = Observer()
        self.observer.schedule(TargetFileHandler(self), path=target_dir, recursive=False)
        self.observer.start()

    def trigger_check(self):
        if not self._check_lock.acquire(blocking=False):
            return  # skip if already running
        try:
            # Show file lines instantly BEFORE submitting
            self._fast_preview()
            # Submit new entries
            try:
                submit_new_entries(self.log_file, self.case_id)
            except Exception as e:
                print(f"⚠️ Submit error: {e}")
            # Full verify after submit
            self.verify_per_entry()
        finally:
            self._check_lock.release()

    def _fast_preview(self):
        """Instantly show file lines with PENDING status before blockchain confirms."""
        try:
            if not os.path.exists(self.log_file):
                return
            with open(self.log_file, "r") as f:
                file_lines = [line for line in f.readlines() if line.strip()]

            chain_count = 0
            if self.v2_ready:
                try:
                    chain_count = self.contract_v2.functions.getEntryCount(self.case_id).call()
                except:
                    pass

            rows = []
            for i, line in enumerate(file_lines):
                fhash = sha256_line(line)
                if i < chain_count:
                    try:
                        chash = self.contract_v2.functions.getEntryHash(self.case_id, i).call()
                        if fhash == chash:
                            rows.append({
                                "index": i, "status": "✅ OK",
                                "content": line.strip()[:55],
                                "file_hash": fhash[:20] + "…",
                                "chain_hash": chash[:20] + "…",
                                "row_class": "", "tag_class": "tag-ok"
                            })
                        else:
                            rows.append({
                                "index": i, "status": "🚨 TAMPERED",
                                "content": line.strip()[:55],
                                "file_hash": fhash[:20] + "…",
                                "chain_hash": chash[:20] + "…",
                                "row_class": "row-tampered", "tag_class": "tag-tampered"
                            })
                    except:
                        rows.append({
                            "index": i, "status": "⏳ PENDING",
                            "content": line.strip()[:55],
                            "file_hash": fhash[:20] + "…", "chain_hash": "...",
                            "row_class": "row-pending", "tag_class": "tag-pending"
                        })
                else:
                    rows.append({
                        "index": i, "status": "⏳ PENDING",
                        "content": line.strip()[:55],
                        "file_hash": fhash[:20] + "…", "chain_hash": "...",
                        "row_class": "row-pending", "tag_class": "tag-pending"
                    })

            self.results_cache = {
                "status": "Scanning...",
                "all_ok": False,
                "file_count": len(file_lines),
                "chain_count": chain_count,
                "rows": rows
            }
        except Exception as e:
            print(f"Preview error: {e}")

    def verify_per_entry(self):
        if not self.v2_ready:
            self.results_cache["status"] = "V2 Contract offline"
            return
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r") as f:
                    file_lines = [line for line in f.readlines() if line.strip()]
            else:
                file_lines = []

            file_count  = len(file_lines)
            chain_count = self.contract_v2.functions.getEntryCount(self.case_id).call()
            max_idx     = max(file_count, chain_count)
            rows        = []
            all_ok      = True

            for i in range(max_idx):
                has_file  = i < file_count
                has_chain = i < chain_count

                if has_file and has_chain:
                    fhash = sha256_line(file_lines[i])
                    chash = self.contract_v2.functions.getEntryHash(self.case_id, i).call()
                    if fhash == chash:
                        rows.append({
                            "index": i, "status": "✅ OK",
                            "content": file_lines[i].strip()[:55],
                            "file_hash": fhash[:20] + "…",
                            "chain_hash": chash[:20] + "…",
                            "row_class": "", "tag_class": "tag-ok"
                        })
                    else:
                        all_ok = False
                        rows.append({
                            "index": i, "status": "🚨 TAMPERED",
                            "content": file_lines[i].strip()[:55],
                            "file_hash": fhash[:20] + "…",
                            "chain_hash": chash[:20] + "…",
                            "row_class": "row-tampered", "tag_class": "tag-tampered"
                        })
                elif has_file and not has_chain:
                    all_ok = False
                    fhash = sha256_line(file_lines[i])
                    rows.append({
                        "index": i, "status": "⏳ PENDING",
                        "content": file_lines[i].strip()[:55],
                        "file_hash": fhash[:20] + "…", "chain_hash": "...",
                        "row_class": "row-pending", "tag_class": "tag-pending"
                    })
                elif has_chain and not has_file:
                    all_ok = False
                    chash = self.contract_v2.functions.getEntryHash(self.case_id, i).call()
                    rows.append({
                        "index": i, "status": "❌ DELETED",
                        "content": "(missing from file)",
                        "file_hash": "(none)",
                        "chain_hash": chash[:20] + "…",
                        "row_class": "row-deleted", "tag_class": "tag-deleted"
                    })

            self.results_cache = {
                "status": "All verified" if all_ok else "Integrity Issues",
                "all_ok": all_ok,
                "file_count": file_count,
                "chain_count": chain_count,
                "rows": rows
            }
        except Exception as e:
            self.results_cache["status"] = f"Error: {e}"
            self.results_cache["all_ok"] = False

    def start(self):
        self.update_target()
        def background_poll():
            while True:
                time.sleep(10)
                threading.Thread(target=self.trigger_check, daemon=True).start()
        threading.Thread(target=background_poll, daemon=True).start()

if __name__ == "__main__":
    monitor = LogMonitor("/home/sura/logchain/config.json")
    monitor.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
