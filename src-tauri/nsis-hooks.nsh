!macro _VIDEO_TIHUAN_STOP_PROCESS PROCESS_NAME
  DetailPrint "Stopping ${PROCESS_NAME} if it is running..."
  nsExec::ExecToStack '"$SYSDIR\taskkill.exe" /F /T /IM "${PROCESS_NAME}"'
  Pop $0
  Pop $1
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro _VIDEO_TIHUAN_STOP_PROCESS "video-tihuan-engine.exe"
  !insertmacro _VIDEO_TIHUAN_STOP_PROCESS "video-tihuan.exe"
  !insertmacro _VIDEO_TIHUAN_STOP_PROCESS "绿幕视频替换.exe"
  Sleep 1000
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro _VIDEO_TIHUAN_STOP_PROCESS "video-tihuan-engine.exe"
  !insertmacro _VIDEO_TIHUAN_STOP_PROCESS "video-tihuan.exe"
  !insertmacro _VIDEO_TIHUAN_STOP_PROCESS "绿幕视频替换.exe"
  Sleep 1000
!macroend
