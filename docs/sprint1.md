Priority    Improvement                              Why
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0          Fix dashboard GitHub gateway scoping     Default dashboard services create
                                                     GitHubIssueGateway() without cwd,
                                                     while only /api/issues patches _cwd
                                                     privately in src/bersama/
                                                     dashboard.py:347. POST actions may
                                                     run gh in the wrong repo when serving
                                                     multiple repos or launched elsewhere.
──────────  ───────────────────────────────────────  ───────────────────────────────────────
P0          Harden background execution lifecycle    src/bersama/dashboard.py:103 only
                                                     reconciles after successful
                                                     execution, and setup failures in src/
                                                     bersama/execution.py:243 do not
                                                     reliably write failed run-state.json.
                                                     Add try/finally, reconcile on all
                                                     terminal states, and persist setup
                                                     failures.
