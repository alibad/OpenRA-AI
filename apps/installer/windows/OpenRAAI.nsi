Unicode true

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

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
!ifndef AIPACKURL
  !error "AIPACKURL must be supplied"
!endif
!ifndef AIPACKSHA256
  !error "AIPACKSHA256 must be supplied"
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

!ifdef UNINSTALLSIGNER
  !uninstfinalize 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${UNINSTALLSIGNER}" -Paths "%1" -RequireSignatures' = 0
!endif

Var AIOptionsDialog
Var RadioLocalAI
Var RadioExternalAI
Var EndpointInput
Var KeyInput
Var ModelInput
Var InstallLocalAI
Var ExternalEndpoint
Var ExternalKey
Var ExternalModel
Var SilentInstall

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
Page custom AIOptionsCreate AIOptionsLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Play-OpenRAAI.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Launch OpenRA AI"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Function .onInit
  StrCpy $InstallLocalAI "1"
  StrCpy $ExternalEndpoint "https://api.openai.com/v1"
  StrCpy $ExternalKey ""
  StrCpy $ExternalModel "gpt-4.1-mini"
  StrCpy $SilentInstall "0"
  IfSilent 0 ai_init_done
  StrCpy $InstallLocalAI "0"
  StrCpy $SilentInstall "1"
ai_init_done:
FunctionEnd

Function AIOptionsCreate
  nsDialogs::Create 1018
  Pop $AIOptionsDialog
  ${If} $AIOptionsDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 28u "Choose how OpenRA AI should answer and speak. Rerun setup later if you want to change providers."
  Pop $0

  ${NSD_CreateRadioButton} 0 32u 100% 22u "Local AI (recommended) — no API key or usage fees"
  Pop $RadioLocalAI
  ${NSD_Check} $RadioLocalAI
  ${NSD_OnClick} $RadioLocalAI AIOptionChanged

  ${NSD_CreateLabel} 14u 52u 94% 24u "Downloads 1.8 GB during setup. Requires about 5 GB free disk; 8 GB RAM minimum, 16 GB recommended. This pack runs on the CPU."
  Pop $0

  ${NSD_CreateRadioButton} 0 78u 100% 18u "External or existing OpenAI-compatible provider"
  Pop $RadioExternalAI
  ${NSD_OnClick} $RadioExternalAI AIOptionChanged

  ${NSD_CreateLabel} 14u 101u 25% 12u "Endpoint"
  Pop $0
  ${NSD_CreateText} 31% 98u 69% 14u "$ExternalEndpoint"
  Pop $EndpointInput

  ${NSD_CreateLabel} 14u 123u 25% 12u "API key"
  Pop $0
  ${NSD_CreatePassword} 31% 120u 69% 14u "$ExternalKey"
  Pop $KeyInput

  ${NSD_CreateLabel} 14u 145u 25% 12u "Model"
  Pop $0
  ${NSD_CreateText} 31% 142u 69% 14u "$ExternalModel"
  Pop $ModelInput

  ${NSD_CreateLabel} 14u 164u 86% 26u "The key is protected with Windows user encryption. Leave it blank for local endpoints such as LM Studio or Ollama."
  Pop $0

  Call AIOptionChanged
  nsDialogs::Show
FunctionEnd

Function AIOptionChanged
  ${NSD_GetState} $RadioExternalAI $0
  ${If} $0 == ${BST_CHECKED}
    EnableWindow $EndpointInput 1
    EnableWindow $KeyInput 1
    EnableWindow $ModelInput 1
  ${Else}
    EnableWindow $EndpointInput 0
    EnableWindow $KeyInput 0
    EnableWindow $ModelInput 0
  ${EndIf}
FunctionEnd

Function AIOptionsLeave
  ${NSD_GetState} $RadioLocalAI $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $InstallLocalAI "1"
  ${Else}
    StrCpy $InstallLocalAI "0"
    ${NSD_GetText} $EndpointInput $ExternalEndpoint
    ${NSD_GetText} $KeyInput $ExternalKey
    ${NSD_GetText} $ModelInput $ExternalModel
    ${If} $ExternalEndpoint == ""
      MessageBox MB_ICONEXCLAMATION "Enter an OpenAI-compatible endpoint."
      Abort
    ${EndIf}
    ${If} $ExternalModel == ""
      MessageBox MB_ICONEXCLAMATION "Enter the model name exposed by your provider."
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Section "OpenRA AI" SEC_MAIN
  SectionIn RO
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*.*"

  ${If} $SilentInstall == "1"
    DetailPrint "Silent install: AI provider configuration skipped."
  ${ElseIf} $InstallLocalAI == "1"
    DetailPrint "Downloading and verifying the local AI pack (about 1.8 GB)..."
    nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\apps\launcher\Install-AIPack.ps1" -Url "${AIPACKURL}" -SHA256 "${AIPACKSHA256}" -Destination "$INSTDIR\ai"'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_ICONSTOP "The local AI pack could not be downloaded or verified. Setup will stop without leaving an unverified model payload."
      Abort
    ${EndIf}
    nsExec::ExecToLog '"$INSTDIR\bin\openra-ai-runtime.exe" configure --mode local'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_ICONSTOP "Local AI configuration failed."
      Abort
    ${EndIf}
  ${Else}
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "mode" "external"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "endpoint" "$ExternalEndpoint"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "api_key" "$ExternalKey"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "text_model" "$ExternalModel"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "vision_model" "$ExternalModel"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "transcribe_model" "whisper-1"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "speech_model" "gpt-4o-mini-tts"
    WriteINIStr "$PLUGINSDIR\openra-ai-provider.ini" "provider" "speech_voice" "alloy"
    nsExec::ExecToLog '"$INSTDIR\bin\openra-ai-runtime.exe" configure --input-ini "$PLUGINSDIR\openra-ai-provider.ini"'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_ICONSTOP "External AI provider configuration failed."
      Abort
    ${EndIf}
  ${EndIf}

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
