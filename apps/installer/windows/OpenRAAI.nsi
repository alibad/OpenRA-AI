Unicode true

!include "MUI2.nsh"

!ifndef VERSION
  !error "VERSION must be supplied"
!endif
!ifndef PAYLOAD
  !error "PAYLOAD must be supplied"
!endif
!ifndef OUTFILE
  !error "OUTFILE must be supplied"
!endif
!ifndef ICON
  !error "ICON must be supplied"
!endif

!define PRODUCT_NAME "OpenRA AI"
!define COMPANY_NAME "RTS AI"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenRA AI"
!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING

Name "${PRODUCT_NAME} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\OpenRA AI"
InstallDirRegKey HKCU "${UNINSTALL_KEY}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "RTS AI"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Play-OpenRAAI.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Launch OpenRA AI"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "OpenRA AI" SEC_MAIN
  SectionIn RO
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*.*"

  WriteUninstaller "$INSTDIR\Uninstall OpenRA AI.exe"

  CreateDirectory "$SMPROGRAMS\OpenRA AI"
  CreateShortcut "$SMPROGRAMS\OpenRA AI\OpenRA AI.lnk" "$INSTDIR\Play-OpenRAAI.cmd" "" "$INSTDIR\assets\brand\rtsai.ico" 0 SW_SHOWNORMAL "" "Launch OpenRA AI"
  CreateShortcut "$DESKTOP\OpenRA AI.lnk" "$INSTDIR\Play-OpenRAAI.cmd" "" "$INSTDIR\assets\brand\rtsai.ico" 0 SW_SHOWNORMAL "" "Launch OpenRA AI"
  CreateShortcut "$SMPROGRAMS\OpenRA AI\Uninstall OpenRA AI.lnk" "$INSTDIR\Uninstall OpenRA AI.exe"

  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${COMPANY_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\assets\brand\rtsai.ico"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall OpenRA AI.exe"'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\OpenRA AI.lnk"
  RMDir /r "$SMPROGRAMS\OpenRA AI"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  RMDir /r "$INSTDIR"
SectionEnd
