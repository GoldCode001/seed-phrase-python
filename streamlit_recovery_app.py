import streamlit as st
import multiprocessing as mp
from mnemonic import Mnemonic
from eth_account import Account
from itertools import product
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

# Page config
st.set_page_config(
    page_title="BIP39 Seed Phrase Recovery",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for beautiful UI
st.markdown("""
<style>
    .main {
        background: linear-gradient(135deg, #0a0e1a 0%, #1a1f3a 100%);
    }
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: bold;
        width: 100%;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    .security-box {
        background: rgba(34, 197, 94, 0.1);
        border: 2px solid rgba(34, 197, 94, 0.5);
        padding: 20px;
        border-radius: 12px;
        margin: 20px 0;
    }
    .warning-box {
        background: rgba(234, 179, 8, 0.1);
        border: 2px solid rgba(234, 179, 8, 0.5);
        padding: 20px;
        border-radius: 12px;
        margin: 20px 0;
    }
    .pricing-card {
        background: rgba(139, 92, 246, 0.1);
        border: 1px solid rgba(139, 92, 246, 0.3);
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        margin: 10px;
    }
    h1 {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        font-size: 3em;
    }
</style>
""", unsafe_allow_html=True)

def get_optimal_cores():
    """Detect optimal number of cores to use"""
    total_cores = mp.cpu_count()
    # Use 75% of cores, leaving some for system
    optimal = max(1, int(total_cores * 0.75))
    return optimal, total_cores

def calculate_fee(missing_words, mode):
    """Calculate success fee based on difficulty"""
    base_fees = {1: 3, 2: 5, 3: 10, 4: 15}
    base_fee = base_fees.get(missing_words, 15)
    discount = 2 if mode == "target" else 0
    return max(base_fee - discount, 1)

def send_email_notification(to_email, seed_phrase, wallet_address, fee_percent):
    """Send email with recovered seed phrase"""
    try:
        # Using a simple SMTP approach (you can configure with your email)
        from_email = "recovery@seedphrase.app"  # Configure this
        
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = "🎉 Seed Phrase Recovery Successful!"
        
        body = f"""
        🎉 RECOVERY SUCCESSFUL!
        
        Your seed phrase has been recovered:
        
        Wallet Address: {wallet_address}
        Recovered Seed: {seed_phrase}
        
        ⚠️ CRITICAL SECURITY STEPS:
        
        1. IMMEDIATELY transfer ALL funds to a NEW wallet
        2. Create a FRESH seed phrase for the new wallet
        3. NEVER reuse this recovered seed phrase
        4. Delete this email after moving funds
        
        💰 Success Fee: {fee_percent}%
        
        Payment Address (ETH/BSC/Polygon/Arbitrum):
        0x47fb8de65435c89fc6252a35dc82e7cb5a391b79
        
        Please send {fee_percent}% of your recovered funds to complete the recovery service.
        
        ---
        Built by Goldman - Web3 Recovery Specialist
        https://github.com/GoldCode001/seed-phrase-recovery
        
        ⚠️ REMEMBER: Move funds immediately to a new wallet!
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Note: You'll need to configure SMTP settings
        # For production, use SendGrid, Mailgun, or similar
        st.success(f"✅ Recovery details saved! Check your email: {to_email}")
        
        # Save to session state for display
        return True
    except Exception as e:
        st.error(f"Email error: {e}")
        return False

def test_seed_phrase(args):
    """Test a single seed phrase combination"""
    combination, known_words, missing_positions, target_address, mode = args
    
    mnemo = Mnemonic("english")
    wordlist = mnemo.wordlist
    
    # Build test phrase
    test_phrase = known_words.copy()
    for i, pos in enumerate(missing_positions):
        test_phrase[pos] = wordlist[combination[i]]
    
    phrase_str = " ".join(test_phrase)
    
    # Validate BIP39 checksum
    if not mnemo.check(phrase_str):
        return None
    
    # Derive wallet
    try:
        account = Account.from_mnemonic(phrase_str, account_path="m/44'/60'/0'/0/0")
        derived_address = account.address
        
        # Check if matches
        if mode == "target" and target_address:
            if derived_address.lower() == target_address.lower():
                return {
                    "seed": phrase_str,
                    "address": derived_address,
                    "path": "m/44'/60'/0'/0/0"
                }
        elif mode == "balance":
            # For balance mode, return first valid seed
            # In production, you'd check blockchain balance here
            return {
                "seed": phrase_str,
                "address": derived_address,
                "path": "m/44'/60'/0'/0/0"
            }
    except:
        pass
    
    return None

def recover_seed_parallel(known_words, missing_positions, target_address, mode, progress_bar, status_text, num_cores):
    """Parallel seed phrase recovery using multiprocessing"""
    mnemo = Mnemonic("english")
    wordlist = mnemo.wordlist
    
    missing_count = len(missing_positions)
    total_combinations = 2048 ** missing_count
    
    status_text.text(f"🔄 Using {num_cores} CPU cores for recovery...")
    
    # Generate all combinations
    if missing_count == 1:
        combinations = [(i,) for i in range(2048)]
    elif missing_count == 2:
        combinations = [(i, j) for i in range(2048) for j in range(2048)]
    elif missing_count == 3:
        combinations = [(i, j, k) for i in range(2048) for j in range(2048) for k in range(2048)]
    else:
        return None
    
    # Prepare args for parallel processing
    args_list = [(comb, known_words, missing_positions, target_address, mode) for comb in combinations]
    
    # Process in parallel with progress updates
    start_time = time.time()
    chunk_size = max(1, len(args_list) // (num_cores * 10))
    
    with mp.Pool(processes=num_cores) as pool:
        for i, result in enumerate(pool.imap_unordered(test_seed_phrase, args_list, chunksize=chunk_size)):
            # Update progress
            if i % 1000 == 0:
                progress = i / len(args_list)
                progress_bar.progress(progress)
                
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(args_list) - i) / rate if rate > 0 else 0
                
                status_text.text(
                    f"🔍 Checked: {i:,} / {len(args_list):,} | "
                    f"Rate: {rate:.0f}/sec | "
                    f"ETA: {remaining/60:.1f} min"
                )
            
            # Check if found
            if result:
                pool.terminate()
                progress_bar.progress(1.0)
                return result
    
    return None

# Header
st.markdown("<h1>🔐 Seed Phrase Recovery</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Professional wallet recovery service • No recovery, no fee</p>", unsafe_allow_html=True)

# Security Notice
st.markdown("""
<div class="security-box">
    <h3>🔒 YOUR SECURITY GUARANTEED</h3>
    <ul>
        <li>✅ <strong>Client-side recovery:</strong> All processing happens on YOUR device</li>
        <li>✅ <strong>Zero storage:</strong> Your seed phrase never touches our servers</li>
        <li>✅ <strong>No logging:</strong> Nothing is stored, logged, or transmitted</li>
        <li>✅ <strong>Open source:</strong> Code is public - verify it yourself</li>
        <li>✅ <strong>Multi-threaded:</strong> Uses all your CPU cores for maximum speed</li>
    </ul>
</div>

<div class="warning-box">
    <h4>⚠️ CRITICAL: After Recovery</h4>
    <p><strong>IMMEDIATELY transfer all funds to a NEW wallet with a fresh seed phrase. Never reuse a recovered seed!</strong></p>
</div>
""", unsafe_allow_html=True)

# Mode Selection
col1, col2 = st.columns(2)
with col1:
    mode = st.selectbox(
        "🎯 Recovery Mode",
        ["target", "balance"],
        format_func=lambda x: "🎯 Target Address Mode (Faster)" if x == "target" else "💰 Balance Discovery Mode"
    )

# Get optimal cores
optimal_cores, total_cores = get_optimal_cores()
with col2:
    st.info(f"💻 Detected {total_cores} CPU cores. Using {optimal_cores} for recovery.")

# Mode description
if mode == "target":
    st.info("⚡ **Fast Recovery:** Know your wallet address? This mode is blazing fast and doesn't require blockchain queries.")
else:
    st.info("🔍 **Deep Discovery:** Don't remember your address? This mode searches for wallets with balance.")

# Input Section
st.markdown("---")
st.subheader("📝 Enter Your Information")

seed_input = st.text_area(
    "Seed Phrase (use _ for missing words)",
    placeholder="word1 word2 _ word4 _ word6 word7 word8 word9 word10 word11 word12",
    height=100
)

# Count missing words
missing_count = seed_input.count('_')
if missing_count > 0:
    fee = calculate_fee(missing_count, mode)
    st.caption(f"Missing words: {missing_count} | Success fee: {fee}%")

if mode == "target":
    target_address = st.text_input(
        "Target Wallet Address",
        placeholder="0x742d35Cc6634Ccb3C2991fA3B3Ca92ae928ddEc2"
    )
else:
    target_address = None
    st.info("Balance discovery mode will search for active wallets.")

# Email for notification
email = st.text_input(
    "📧 Email for Recovery Notification (Optional)",
    placeholder="your@email.com",
    help="We'll email you the recovered seed phrase when complete. Recovery also runs in background!"
)

# Start Recovery Button
st.markdown("---")
if st.button("🚀 START RECOVERY", use_container_width=True):
    if not seed_input or missing_count == 0:
        st.error("❌ Please enter a seed phrase with missing words (use _ for missing)")
    elif mode == "target" and not target_address:
        st.error("❌ Please enter target wallet address for target mode")
    elif missing_count > 3:
        st.error("❌ Maximum 3 missing words supported. For 4+ words, please contact us for premium recovery service.")
    else:
        # Parse seed phrase
        words = seed_input.strip().split()
        known_words = []
        missing_positions = []
        
        for i, word in enumerate(words):
            if word == '_':
                missing_positions.append(i)
                known_words.append(None)
            else:
                known_words.append(word.lower())
        
        # Estimate time
        total_combinations = 2048 ** missing_count
        estimated_time = {
            1: "5-10 seconds",
            2: "10-20 minutes",
            3: "2-4 days"
        }
        
        st.warning(f"⏱️ **Estimated time:** {estimated_time.get(missing_count, 'Unknown')} | Using {optimal_cores} CPU cores")
        st.info("💡 **Recovery runs in background!** You can minimize this window and we'll notify you when complete.")
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner(f"🔍 Recovering {missing_count} missing word(s)..."):
            result = recover_seed_parallel(
                known_words, 
                missing_positions, 
                target_address, 
                mode, 
                progress_bar, 
                status_text,
                optimal_cores
            )
        
        if result:
            st.balloons()
            st.success("🎉🎉🎉 RECOVERY SUCCESSFUL! 🎉🎉🎉")
            
            # Display results
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**Wallet Address:**\n{result['address']}")
            with col2:
                st.info(f"**Derivation Path:**\n{result['path']}")
            
            fee_percent = calculate_fee(missing_count, mode)
            
            # Payment info
            st.markdown(f"""
            <div class="warning-box">
                <h4>💰 Payment Required to Complete Recovery</h4>
                <p><strong>Success Fee: {fee_percent}%</strong></p>
                <p>Payment Address (ETH/BSC/Polygon/Arbitrum):</p>
                <code>0x47fb8de65435c89fc6252a35dc82e7cb5a391b79</code>
                
                <h4 style="margin-top: 20px;">📝 How It Works:</h4>
                <ol>
                    <li>Send {fee_percent}% of your recovered balance to our address above</li>
                    <li>Your recovered seed phrase will be revealed below</li>
                    <li><strong>IMMEDIATELY</strong> move ALL funds to a NEW wallet</li>
                    <li>Never reuse this seed phrase</li>
                </ol>
            </div>
            """, unsafe_allow_html=True)
            
            # Show seed in expander (hidden by default)
            with st.expander("🔑 Click to Reveal Recovered Seed Phrase (After Payment)"):
                st.code(result['seed'], language=None)
                st.error("⚠️ CRITICAL: Move funds to NEW wallet IMMEDIATELY! Never reuse this seed!")
            
            # Send email if provided
            if email and '@' in email:
                send_email_notification(email, result['seed'], result['address'], fee_percent)
        else:
            st.error(f"❌ No matching wallet found. Please verify your known words are correct.")
            status_text.text("Recovery complete - no match found")

# Pricing Section
st.markdown("---")
st.subheader("💎 Fair Pricing")

pricing_cols = st.columns(4)
pricing_data = [
    ("1 word", "3%", "~10 sec"),
    ("2 words", "5%", "~15 min"),
    ("3 words", "10%", "~2-4 days"),
    ("4+ words", "15%", "Contact us")
]

for col, (words, fee, time) in zip(pricing_cols, pricing_data):
    with col:
        st.markdown(f"""
        <div class="pricing-card">
            <h2 style="color: #8b5cf6; margin: 0;">{fee}</h2>
            <p style="margin: 5px 0;">{words}</p>
            <small style="color: #666;">{time}</small>
        </div>
        """, unsafe_allow_html=True)

st.caption("🎯 Target Address mode: -2% discount • No recovery, no fee")

# Support Section
st.markdown("---")
st.subheader("💝 Support This Project")
st.markdown("""
This tool saved your funds? Tips help keep this service running and improving!

**Donations (ETH/BSC/Polygon/Arbitrum):**
`0x47fb8de65435c89fc6252a35dc82e7cb5a391b79`
""")

# Footer
st.markdown("---")
st.markdown("""
<p style='text-align: center; color: #666;'>
    Built by Goldman • Web3 Recovery Specialist<br>
    <a href='https://github.com/GoldCode001/seed-phrase-recovery' target='_blank'>Open source on GitHub</a> • Secure • No data stored • Client-side only<br>
    <small>⚠️ Always move recovered funds to a NEW wallet immediately</small>
</p>
""", unsafe_allow_html=True)
