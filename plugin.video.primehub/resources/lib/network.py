"""
Network utility functions for making API calls, conforming to API_DOCS.md.
"""
from __future__ import annotations
import sys
import os
from typing import Optional, Dict, Tuple

# Add vendor directory to sys.path for bundled libraries
vendor_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'vendor'))
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

import requests
import mechanicalsoup
from .session import SessionManager

try:
    import xbmc
except ImportError:
    from ...tests.kodi_mocks import xbmc

def _log(level: int, message: str) -> None:
    xbmc.log(f"[PrimeHub-Network] {message}", level)

def MechanizeLogin(username, password) -> requests.Session:
    """
    Performs the live, multi-step login process.
    NOTE: This does not handle MFA or Captcha. A developer must add that logic.
    """
    _log(xbmc.LOGINFO, f"MechanizeLogin (LIVE) for user {username}")
    
    session = SessionManager.get_instance().get_session()
    br = mechanicalsoup.StatefulBrowser(
        session=session,
        soup_config={'features': 'html.parser'}
    )
    
    # 1. Open the Amazon sign-in page
    login_url = "https://www.amazon.com/ap/signin"
    try:
        br.open(login_url, timeout=15)
    except Exception as e:
        _log(xbmc.LOGERROR, f"Failed to open login page: {e}")
        return session

    # 2. Select the sign-in form and fill in credentials
    try:
        br.select_form('form[name="signIn"]')
        br["email"] = username
        br["password"] = password
        br.submit_selected()
    except mechanicalsoup.LinkNotFoundError:
        _log(xbmc.LOGERROR, "Could not find the sign-in form.")
        return session 

    # 3. Check for MFA/Captcha and handle it (DEVELOPER ACTION REQUIRED)
    response_html = str(br.get_current_page())
    if "auth-mfa-form" in response_html or "ap_captcha_img" in response_html:
        _log(xbmc.LOGINFO, "MFA or Captcha detected. Developer intervention required.")
        # DEVELOPER: You would trigger a UI window here to ask the user
        # for the OTP code or Captcha solution, then submit the new form.
        return session

    # 4. On success, the session object passed to the browser is updated by reference.
    _log(xbmc.LOGINFO, "Login successful, session cookies should be obtained.")
    SessionManager.get_instance().save_session()
    
    return session

def GrabJSON(url: str, postData: Optional[Dict] = None) -> Dict:
    _log(xbmc.LOGINFO, f"GrabJSON (LIVE) from {url}")
    session = SessionManager.get_instance().get_session()
    try:
        response = session.get(url, data=postData, timeout=15)
        response.raise_for_status()
        # This is still a placeholder. The Sandmann79 code shows that JSON is often
        # embedded in script tags within the HTML, requiring careful parsing.
        # DEVELOPER: Implement HTML parsing here to extract the JSON.
        return response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        _log(xbmc.LOGERROR, f"GrabJSON failed for {url}: {e}")
        return {}

def getURLData(mode: str, asin: str, **kwargs) -> Tuple[bool, Dict | str]:
    _log(xbmc.LOGINFO, f"getURLData (LIVE) for {mode} with asin {asin}")
    session = SessionManager.get_instance().get_session()
    
    # This URL and the params are based on Sandmann79 analysis
    base_url = "https://atv-ps.amazon.com/cdp/"
    params = {
        "asin": asin,
        "deviceTypeID": "A1F83G8C2ARO7P", # Example ID, should be configurable
        "firmware": "1",
        "format": "json",
        "marketplaceID": "ATVPDKIKX0DER", # Example ID, should be configurable
        **kwargs
    }
    
    try:
        response = session.get(base_url + mode, params=params, timeout=15)
        response.raise_for_status()
        return (True, response.json())
    except requests.exceptions.RequestException as e:
        _log(xbmc.LOGERROR, f"getURLData failed for {mode} with asin {asin}: {e}")
        return (False, str(e))