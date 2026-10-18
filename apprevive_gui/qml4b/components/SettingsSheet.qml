import QtQuick
import QtQuick.Controls.Basic as Basic
import "../theme"

// «Настройки» (02-picker §6b): «Поиск» — «Искать в архиве» (on by default,
// applied at once) with Лена's caption; «Обновления» — the old window's check.
Sheet {
    id: root
    objectName: "settingsSheet"
    readonly property var s: ui.settings
    title: root.s.title || ""
    cancelText: root.s.close || "Закрыть"
    panelWidth: Theme.authSheetWidth
    onCancel: ui.closeSettings()

    Flickable {
        width: parent.width
        height: Math.min(settingsContent.implicitHeight, Math.max(160, root.height - 180))
        contentHeight: settingsContent.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
    Column {
        id: settingsContent
        width: parent.width
        spacing: 0
        // -- Поиск
        T { token: "group"; text: root.s.searchTitle || "" }
        Item { width: 1; height: 8 }
        Rectangle { width: parent.width; height: 1; color: Theme.ink }
        Item { width: 1; height: 12 }
        Basic.Switch {
            id: archive
            objectName: "archiveSwitch"
            checked: !!root.s.archive
            text: root.s.archiveSwitch || ""
            leftPadding: 0
            font.family: Theme.fontFamily
            font.pixelSize: Theme.style("row").size
            onToggled: ui.setArchiveSearch(checked)
            Accessible.name: text
        }
        Item { width: 1; height: 8 }
        T {
            width: parent.width
            token: "fine"
            color: Theme.ink2
            wrapMode: Text.WordWrap
            text: root.s.archiveNote || ""
        }
        Item { width: 1; height: 28 }
        // -- Обновления
        T { token: "group"; text: root.s.updatesTitle || "" }
        Item { width: 1; height: 8 }
        Rectangle { width: parent.width; height: 1; color: Theme.ink }
        Item { width: 1; height: 12 }
        Cta {
            objectName: "checkUpdates"
            secondary: true
            compact: true
            enabledLook: !root.s.updateBusy
            text: root.s.checkUpdates || ""
            onClicked: ui.checkUpdates()
        }
        Item { width: 1; height: 8; visible: updateText.visible }
        T {
            id: updateText
            objectName: "updateStatus"
            visible: text !== ""
            width: parent.width
            token: "status"
            color: Theme.ink2
            wrapMode: Text.WordWrap
            text: root.s.updateStatus || ""
        }
        Item { width: 1; height: 24 }
        T { token: "group"; text: "Очистка данных" }
        Item { width: 1; height: 12 }
        Cta {
            objectName: "clearAppleAccounts"
            secondary: true; compact: true
            text: "Очистить аккаунты Apple"
            enabledLook: !!root.s.cleanupEnabled
            onClicked: ui.askCleanup("accounts")
        }
        Item { width: 1; height: 12 }
        Cta {
            objectName: "clearDownloads"
            secondary: true; compact: true
            text: "Удалить скачанные IPA"
            enabledLook: !!root.s.cleanupEnabled
            onClicked: ui.askCleanup("downloads")
        }
        Item { width: 1; height: 12 }
        T {
            width: parent.width; token: "fine"; wrapMode: Text.WordWrap
            text: root.s.cleanupKind === "accounts"
                ? "Удалить все сохранённые аккаунты Apple и завершить текущий вход?"
                : root.s.cleanupKind === "downloads"
                  ? "Навсегда удалить скачанные IPA из папки AppRevive с диска? Файлы, выбранные из других папок, сохранятся."
                  : ""
            visible: text !== ""
        }
        Row {
            spacing: 12
            visible: !!root.s.cleanupKind
            Cta { objectName: "confirmCleanup"; compact: true; text: "Удалить"; onClicked: ui.confirmCleanup() }
            Cta { compact: true; secondary: true; text: "Отмена"; onClicked: ui.cancelCleanup() }
        }
        T {
            objectName: "cleanupStatus"
            width: parent.width; token: "status"; wrapMode: Text.WordWrap
            text: root.s.cleanupStatus || ""
            visible: text !== ""
        }
    }
    }
}
