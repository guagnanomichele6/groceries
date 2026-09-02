import streamlit as st
import os
import shutil

def render_settings_tab(db_name, create_backup_callback):
    st.header("Impostazioni & Sicurezza")
    st.subheader("💾 Gestione Backup Database")
    st.caption("Crea una copia di sicurezza del database o ripristina uno stato precedente.")
    
    if st.button("📥 Crea Backup Manuale Adesso"):
        b_file = create_backup_callback()
        st.success(f"Backup creato in: `{b_file}`")
        
    st.divider()
    st.markdown("**Backup Disponibili:**")
    if os.path.exists("backups"):
        backups = sorted(os.listdir("backups"), reverse=True)
        if backups:
            selected_backup = st.selectbox("Seleziona backup da ripristinare", backups)
            if st.button("🔄 Ripristina questo Backup"):
                shutil.copy(f"backups/{selected_backup}", db_name)
                st.success(f"Database ripristinato con successo da `{selected_backup}`!")
                st.rerun()
        else:
            st.info("Nessun backup presente.")
    else:
        st.info("Cartella backup vuota.")