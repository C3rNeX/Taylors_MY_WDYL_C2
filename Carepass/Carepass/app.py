import hashlib
import hmac
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

# To run the web app ----> Enter this in terminal: python -m streamlit run app.py
# ==============================================================================
# 1. MOCK TIDECLOAK IAM & THRESHOLD CRYPTOGRAPHY MIDDLEMAN
# ==============================================================================
class TideCloak:
    """
    SIMULATED COMPONENT (Identified per Challenge 2 Guidelines):
    Mocks TideCloak's decentralized Identity & Access Management (IAM) and
    Threshold Cryptography / Distributed Key Generation (DKG) network.

    Key Custody Guarantee:
    - The application server and raw database NEVER hold decryption keys.
    - Data is encrypted into a scrambled hex ciphertext before touching storage.
    - Decryption is strictly gated by TideCloak's policy engine and only releases
      plaintext when presented with an authorized 'Doctor' role context.
    """

    # Simulated decentralized threshold key (never exposed to the database layer)
    _ENCLAVE_MASTER_SECRET = b"TideCloak-DKG-Threshold-Enclave-Secret-2026-RMIT"

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        """Generates a deterministic cryptographic keystream from the enclave secret."""
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block = hmac.new(
                self._ENCLAVE_MASTER_SECRET,
                nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])

    def encrypt(self, data: str) -> str:
        """
        Encrypts plaintext into a scrambled hexadecimal string.
        Even if an attacker converts the hex back to bytes, the payload remains
        cryptographically scrambled without TideCloak's threshold keystream.
        """
        if not isinstance(data, str):
            data = str(data)
        plaintext_bytes = data.encode("utf-8")
        nonce = hmac.new(
            self._ENCLAVE_MASTER_SECRET, plaintext_bytes, hashlib.sha256
        ).digest()[:8]
        mask = self._keystream(nonce, len(plaintext_bytes))
        ciphertext_bytes = bytes(b ^ m for b, m in zip(plaintext_bytes, mask))
        return (nonce + ciphertext_bytes).hex()

    def decrypt(self, hash: str, role: str) -> str:
        """
        Evaluates role-based authority via TideCloak IAM policy:
        - Returns the original plaintext ONLY if role == 'Doctor'.
        - Otherwise returns 'Access Denied' (including for 'Admin' or DB owners).
        """
        if role != "Doctor":
            return "Access Denied"

        try:
            raw = bytes.fromhex(hash)
            if len(raw) < 8:
                return "Invalid Ciphertext"
            nonce, ciphertext_bytes = raw[:8], raw[8:]
            mask = self._keystream(nonce, len(ciphertext_bytes))
            plaintext_bytes = bytes(c ^ m for c, m in zip(ciphertext_bytes, mask))
            return plaintext_bytes.decode("utf-8")
        except Exception:
            return "Decryption Error: Corrupted Ciphertext"


# ==============================================================================
# 2. PAGE CONFIGURATION & STYLING
# ==============================================================================
st.set_page_config(
    page_title="MedVault | TideCloak Zero-Custody EHR",
    page_icon="🛡️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background-color: #0b1120;
        color: #f8fafc;
    }
    .hero-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-left: 5px solid #2dd4bf;
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        margin-bottom: 1.2rem;
    }
    .sim-banner {
        background-color: rgba(245, 158, 11, 0.12);
        border: 1px solid #f59e0b;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.9rem;
        color: #fde68a;
        margin-bottom: 1.2rem;
    }
    .status-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# 3. SESSION STATE INITIALIZATION & HELPER FUNCTIONS
# ==============================================================================
tidecloak = TideCloak()

if "medical_records" not in st.session_state:
    # Seed initial encrypted records using TideCloak BEFORE saving to session_state
    seed_entries = [
        "Patient #1042 (Aria Chen): Acute migraine & penicillin allergy. Prescribed Sumatriptan 50mg.",
        "Patient #2089 (Marcus Vance): Type-2 Diabetes HbA1c 7.4%. Continue Metformin 500mg BID.",
    ]
    st.session_state.medical_records = [
        {
            "record_id": f"REC-{1001 + idx}",
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "encrypted_hash": tidecloak.encrypt(entry),
            "key_custody": "TideCloak DKG Enclave (Zero DB Custody)",
        }
        for idx, entry in enumerate(seed_entries)
    ]

if "audit_logs" not in st.session_state:
    st.session_state.audit_logs = [
        {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "actor": "System Bootstrap",
            "action": "ENCRYPT_SEED_RECORDS",
            "outcome": "2 records encrypted via TideCloak before DB storage",
        }
    ]


def log_event(actor: str, action: str, outcome: str) -> None:
    st.session_state.audit_logs.insert(
        0,
        {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "actor": actor,
            "action": action,
            "outcome": outcome,
        },
    )


def verify_doctor_identity(selected_role: str, doctor_name: str) -> tuple[str, str]:
    """
    Requires the user to enter their name when 'Doctor' is selected:
    - If selected_role == 'Doctor' and doctor_name is non-empty, returns
      ('Doctor', 'Dr. <Name> (Doctor)') so TideCloak unlocks decryption.
    - If selected_role == 'Doctor' but doctor_name is empty, returns
      ('Unverified Doctor', 'Unverified Doctor (Name Required)') so TideCloak
      returns 'Access Denied'.
    """
    if selected_role != "Doctor":
        return selected_role, selected_role

    cleaned_name = doctor_name.strip()
    if not cleaned_name:
        return "Unverified Doctor", "Unverified Doctor (Name Required)"

    display_name = cleaned_name if cleaned_name.lower().startswith("dr") else f"Dr. {cleaned_name}"
    return "Doctor", f"{display_name} (Doctor)"


def edit_patient_record(
    record_id: str, updated_plaintext: str, role: str, doctor_label: str = "Role: Doctor"
) -> tuple[bool, str]:
    """
    Role-gated edit function:
    1. Verifies the caller holds the 'Doctor' role via TideCloak policy.
    2. Re-encrypts the updated patient details using TideCloak.encrypt(data)
       BEFORE updating st.session_state.medical_records.
    """
    if role != "Doctor":
        log_event(
            actor=doctor_label,
            action=f"EDIT_DENIED ({record_id})",
            outcome="Blocked: Only a verified 'Doctor' can modify encrypted patient records",
        )
        return False, "Access Denied: Only the 'Doctor' role is authorized to edit records."

    for rec in st.session_state.medical_records:
        if rec["record_id"] == record_id:
            # Re-encrypt BEFORE saving back to session_state
            new_hash = tidecloak.encrypt(updated_plaintext.strip())
            rec["encrypted_hash"] = new_hash
            rec["timestamp_utc"] = (
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} "
                f"(Edited by {doctor_label})"
            )
            log_event(
                actor=doctor_label,
                action=f"EDIT_AND_REENCRYPT ({record_id})",
                outcome=f"Re-encrypted via TideCloak ({len(new_hash)} hex chars)",
            )
            return True, new_hash

    return False, "Record ID not found."


# ==============================================================================
# 4. HEADER & SIMULATED COMPONENT DISCLOSURE (SLIDES 17, 20, 21, 26)
# ==============================================================================
st.markdown(
    """
    <div class="hero-box">
        <h2 style="margin:0; color:#2dd4bf;">🛡️ MedVault — Zero-Custody Clinical Record System</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Encrypted Records in DB", len(st.session_state.medical_records))
col_m2.metric("Database Key Custody", "0% (Zero Custody)")
col_m3.metric("Admin Plaintext Access", "Blocked (Access Denied)")
col_m4.metric("Authorized Decryption Role", "Doctor Only")


# ==============================================================================
# 5. THREE CORE STREAMLIT TABS (PATIENT PORTAL | HACKER VIEW | AUTHORIZED VIEW)
# ==============================================================================
tab1, tab2, tab3 = st.tabs(
    [
        "🏥 Tab 1: Patient Portal",
        "💻 Tab 2: Raw Database (Hacker View)",
        "🔐 Tab 3: Authorized Dashboard",
    ]
)

# ------------------------------------------------------------------------------
# TAB 1: PATIENT PORTAL
# ------------------------------------------------------------------------------
with tab1:
    st.subheader("Patient Portal — Edge Encryption Before Storage")
    st.write(
        "Submit a sensitive medical record below. **MedVault** passes your record to "
        "`TideCloak.encrypt(data)` **before** it ever touches `st.session_state`, ensuring "
        "the database never sees or stores plaintext."
    )

    preset_col1, preset_col2 = st.columns([2, 1])
    with preset_col2:
        preset_choice = st.selectbox(
            "Optional Demo Quick-Fill:",
            [
                "(Type custom record)",
                "Patient #3014 (Elena Rostova): HIV+ viral load undetectable; maintain Biktarvy regimen.",
                "Patient #4110 (Liam O'Connor): Severe anaphylaxis to latex; scheduled for cardiac MRI.",
                "Patient #5092 (Siti Rahmah): Post-op renal transplant; Tacrolimus trough 6.8 ng/mL.",
            ],
        )

    default_text = "" if preset_choice == "(Type custom record)" else preset_choice

    with st.form("patient_record_form", clear_on_submit=True):
        patient_record = st.text_input(
            "Enter Patient Medical Record (Plaintext):",
            value=default_text,
            placeholder="e.g., Patient Jane Doe: Diagnosis, allergies, sensitive lab results...",
        )
        submitted = st.form_submit_button("🔒 Encrypt via TideCloak & Submit Record", type="primary")

        if submitted:
            if not patient_record.strip():
                st.warning("Please enter a medical record before submitting.")
            else:
                # CRITICAL REQUIREMENT: Encrypt BEFORE saving to st.session_state
                encrypted_hex = tidecloak.encrypt(patient_record.strip())
                new_id = f"REC-{1001 + len(st.session_state.medical_records)}"
                timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                st.session_state.medical_records.append(
                    {
                        "record_id": new_id,
                        "timestamp_utc": timestamp_str,
                        "encrypted_hash": encrypted_hex,
                        "key_custody": "TideCloak DKG Enclave (Zero DB Custody)",
                    }
                )
                log_event(
                    actor="Patient Portal",
                    action="ENCRYPT_AND_STORE",
                    outcome=f"Stored {new_id} as scrambled hex ({len(encrypted_hex)} hex chars)",
                )
                st.success(
                    f"✅ Record **{new_id}** encrypted by TideCloak BEFORE saving to database!"
                )
                st.code(f"Ciphertext Stored in DB: {encrypted_hex}", language="text")

    st.divider()
    st.markdown("#### 🔄 How TideCloak Enforces Zero Custody on Submission")
    step_c1, step_c2, step_c3 = st.columns(3)
    with step_c1:
        st.info(
            "**1. Patient Input (In-Memory)**\n\n"
            "Patient enters sensitive health record. Plaintext exists only transiently at the edge."
        )
    with step_c2:
        st.warning(
            "**2. TideCloak `.encrypt(data)`**\n\n"
            "TideCloak scrambles the record into a hex ciphertext using threshold-protected keys."
        )
    with step_c3:
        st.success(
            "**3. Untrusted DB (`st.session_state`)**\n\n"
            "Only the scrambled hex string is appended to `st.session_state`. Zero plaintext custody."
        )


# ------------------------------------------------------------------------------
# TAB 2: RAW DATABASE (HACKER VIEW)
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("Raw Database (Hacker / Compromised Cloud View)")
    st.write(
        "This view displays the raw `st.session_state` medical records inside a **Pandas DataFrame**. "
        "Even if an attacker dumps the database or a rogue cloud administrator inspects the table, "
        "they only see **encrypted hexadecimal gibberish** because the database has **zero custody** "
        "of the decryption keys."
    )

    if st.session_state.medical_records:
        raw_df = pd.DataFrame(
            [
                {
                    "Record ID": rec["record_id"],
                    "Timestamp (UTC)": rec["timestamp_utc"],
                    "Encrypted Payload (Hex Gibberish)": rec["encrypted_hash"],
                    "Key Custody Holder": rec["key_custody"],
                }
                for rec in st.session_state.medical_records
            ]
        )
        st.dataframe(raw_df, use_container_width=True, hide_index=True)

        with st.expander("🕵️ Simulate Hacker Exfiltration / Raw Byte Inspection"):
            st.write(
                "What happens if an attacker steals a ciphertext row from the Pandas DataFrame "
                "and attempts `bytes.fromhex(hash)` without TideCloak's threshold key?"
            )
            sample_hash = st.session_state.medical_records[-1]["encrypted_hash"]
            raw_bytes_preview = repr(bytes.fromhex(sample_hash))
            st.code(
                f"Stolen Hex String : {sample_hash}\n"
                f"Decoded Raw Bytes : {raw_bytes_preview}\n"
                f"Hacker Result     : UNREADABLE CRYPTOGRAPHIC GIBBERISH (0% Key Custody)",
                language="text",
            )
    else:
        st.info("No records in the database yet. Add one in Tab 1: Patient Portal.")


# ------------------------------------------------------------------------------
# TAB 3: AUTHORIZED DASHBOARD (VIEW, DOCTOR NAME CHECK & EDIT PATIENT DETAILS)
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("Authorized Dashboard — Policy-Gated Decryption & Editing")
    st.write(
        "Select an IAM role below to pass every database record through "
        "`TideCloak.decrypt(hash, role)`. Selecting the **Doctor** role requires you to "
        "enter your name before TideCloak unlocks clinical plaintext and editing."
    )

    role_col1, role_col2 = st.columns(2)
    with role_col1:
        selected_role = st.selectbox(
            "Select Active IAM Role:",
            options=["Admin", "Doctor"],
            index=0,
            help="Switch between 'Admin' and 'Doctor' to test TideCloak's role-bound decryption and editing.",
        )

    doctor_name_input = ""
    with role_col2:
        if selected_role == "Doctor":
            doctor_name_input = st.text_input(
                "Enter Doctor Name (Required to Unlock):",
                placeholder="e.g., Sarah Jenkins",
            )

    # Check if 'Doctor' has entered their name
    effective_role, actor_label = verify_doctor_identity(selected_role, doctor_name_input)

    if selected_role == "Doctor" and effective_role != "Doctor":
        st.warning(
            "🪪 **Doctor Name Required** — Please enter your name above to verify your "
            "`Doctor` identity and unlock decryption."
        )
    elif effective_role == "Doctor":
        st.success(
            f"🩺 **Active Role: {actor_label}** — TideCloak verified clinical authority and "
            "released threshold decryption shares."
        )
    else:
        st.error(
            "🚫 **Active Role: Admin** — Infrastructure administrators do NOT have clinical "
            "authority. TideCloak refuses to release decryption shares (`Access Denied`)."
        )

    if st.session_state.medical_records:
        decrypted_rows = []
        for rec in st.session_state.medical_records:
            decrypted_output = tidecloak.decrypt(rec["encrypted_hash"], effective_role)
            decrypted_rows.append(
                {
                    "Record ID": rec["record_id"],
                    "Timestamp (UTC)": rec["timestamp_utc"],
                    "Active Role": actor_label,
                    "TideCloak.decrypt(hash, role) Output": decrypted_output,
                    "Encrypted Hash (Source)": rec["encrypted_hash"][:28] + "...",
                }
            )

        dec_df = pd.DataFrame(decrypted_rows)
        st.dataframe(dec_df, use_container_width=True, hide_index=True)

        # ----------------------------------------------------------------------
        # EDIT PATIENT DETAILS SECTION (GATED BY TIDECLOAK 'Doctor' ROLE + NAME)
        # ----------------------------------------------------------------------
        st.divider()
        st.markdown("#### ✏️ Edit Patient Details (Protected Action)")

        record_ids = [rec["record_id"] for rec in st.session_state.medical_records]
        selected_rec_id = st.selectbox("Select Record ID to Edit:", options=record_ids)

        target_rec = next(
            rec for rec in st.session_state.medical_records if rec["record_id"] == selected_rec_id
        )
        current_decrypted = tidecloak.decrypt(target_rec["encrypted_hash"], effective_role)

        if effective_role != "Doctor":
            st.warning(
                "🔒 **Editing Locked (`Access Denied`)**: Select the **Doctor** role and "
                "enter your **Doctor Name** above to decrypt, edit, and re-encrypt patient details."
            )
            st.text_input(
                "Current Record Content (Encrypted / Locked):",
                value=current_decrypted,
                disabled=True,
            )
        else:
            with st.form("edit_patient_record_form"):
                updated_details = st.text_input(
                    f"Update Clinical Details for {selected_rec_id} (Editing as {actor_label}):",
                    value=current_decrypted,
                )
                save_edit = st.form_submit_button(
                    "💾 Re-Encrypt via TideCloak & Save Changes", type="primary"
                )

                if save_edit:
                    if not updated_details.strip():
                        st.warning("Updated record cannot be empty.")
                    else:
                        ok, result_msg = edit_patient_record(
                            selected_rec_id, updated_details, effective_role, actor_label
                        )
                        if ok:
                            st.success(
                                f"✅ **{selected_rec_id}** updated by **{actor_label}** and re-encrypted via TideCloak!"
                            )
                            st.rerun()
                        else:
                            st.error(result_msg)

        st.divider()
        st.markdown("#### 📋 Record-by-Record Decryption Inspection")
        for row in decrypted_rows:
            status_icon = "🔓" if row["TideCloak.decrypt(hash, role) Output"] != "Access Denied" else "🔒"
            st.markdown(
                f"""
                <div class="status-card">
                    <strong>{status_icon} {row['Record ID']}</strong>
                    <span style="color:#94a3b8; font-size:0.85rem;"> • {row['Timestamp (UTC)']} • Role: <code>{row['Active Role']}</code></span><br/>
                    <span style="color:{'#4ade80' if effective_role == 'Doctor' else '#f87171'}; font-family:monospace; font-size:0.98rem;">
                        {row['TideCloak.decrypt(hash, role) Output']}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No records available to decrypt. Submit a record in Tab 1 first.")


# ==============================================================================
# 6. SIDEBAR: EVALUATION CRITERIA BRIEF & LIVE AUDIT LOG (SLIDES 15-21)
# ==============================================================================
with st.sidebar:
    st.header("🧭 Trust & Custody Architecture")
    st.markdown(
        """
        **1. Real-World Problem**
        Hospitals & cloud EHR platforms suffer catastrophic breaches because *database admins and cloud hosts hold unilateral custody of encryption keys*.

        **2. Privacy & Custody Constraint**
        How can an application store and process patient records when **no single party (not even the System Admin)** can be trusted with raw keys?

        **3. Why TideCloak Matters**
        TideCloak decouples **infrastructure administration (`Admin`)** from **data decryption & modification authority (`Doctor`)**:
        - `encrypt(data)` scrambles records at the edge before DB storage.
        - `decrypt(hash, role)` enforces cryptographic role verification.
        """
    )

    st.divider()
    st.subheader("📜 Live TideCloak Audit Trail")
    for entry in st.session_state.audit_logs[:6]:
        st.caption(
            f"**{entry['time']}** | `{entry['actor']}`  \n"
            f"{entry['action']} → *{entry['outcome']}*"
        )

    st.divider()
    if st.button("🗑️ Reset Mock Database to Defaults"):
        for key in ["medical_records", "audit_logs"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()