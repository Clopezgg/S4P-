// Static preview forwards users to the first-party FastAPI + React application.
// Never copy query parameters, form fields or credentials across origins.
if (window.location.hostname === 's4p-sap-preview.onrender.com') {
  window.location.replace('https://s4p-erp-api.onrender.com/login')
}
