/*
 * View model for OctoPrint-Celestrius
 *
 * Author: Celestrius
 * License: AGPLv3
 */
$(function () {
    function CelestriusViewModel(parameters) {
        var self = this;

        // assign the injected parameters, e.g.:
        self.settingsViewModel = parameters[0];
        self.wizardViewModel = parameters[1];

        self.uploadHistory = ko.observableArray([]);

        self.columns = [
            { headerText: "Column A", rowText: "column_a" },
            { headerText: "Column B", rowText: "column_b" },
        ];

        self.onSettingsShown = function (plugin, data) {
            self.fetchUploadHistory();
        };

        self.isEnabled = ko.pureComputed(function () {
            return (
                self.settingsViewModel.settings.plugins.celestrius.enabled &&
                self.settingsViewModel.settings.plugins.celestrius.enabled()
            );
        });
        self.needConfig = ko.pureComputed(function () {
            return (
                !self.settingsViewModel.settings.plugins.celestrius.terms_accepted() ||
                !self.settingsViewModel.settings.plugins.celestrius.pilot_email() ||
                !self.settingsViewModel.settings.plugins.celestrius.snapshot_url()
            );
        });
        self.navbarBtnClassName = ko.pureComputed(function () {
            var clazz = "pull-right celestrius-toggle";
            if (self.needConfig()) {
                clazz += " need_config";
            }
            if (self.isEnabled()) {
                clazz += " enabled";
            }
            return clazz;
        });

        // TODO: Implement your plugin's view model here.
        self.toggleIsEnabled = function () {
            const newVal =
                !self.settingsViewModel.settings.plugins.celestrius.enabled();
            self.settingsViewModel.settings.plugins.celestrius.enabled(newVal);
            self.settingsViewModel.saveData();
        };
        self.navbarButtonTitle = ko.pureComputed(function () {
            if (self.needConfig()) {
                return "Celestrius is NOT configured properly. Please go to the settings page to configure it.";
            }
            return self.isEnabled()
                ? "Celestrius is collecting data. Click to turn OFF."
                : "Celestrius is NOT collecting data. Click to turn ON.";
        });

        self.termsAccepted = ko.pureComputed(function () {
            return self.settingsViewModel.settings.plugins.celestrius.terms_accepted();
        });
        self.consentText = ko.pureComputed(function () {
            return self.termsAccepted()
                ? "You have accepted the terms for participating in the pilot program."
                : "I understand the privacy policy and accept the terms for participating in the pilot program.";
        });
        self.savePluginSettings = function () {
            self.settingsViewModel.saveData();
            return true;
        };
        self.fetchUploadHistory = function () {
            apiCommand({
                command: "upload_history",
            }).done(function (data) {
                console.log(data);
                self.uploadHistory(data);
            });
        };
    }

    function apiCommand(data) {
        return $.ajax("api/plugin/celestrius", {
            method: "POST",
            contentType: "application/json",
            data: JSON.stringify(data),
        });
    }
    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: CelestriusViewModel,
        // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: ["settingsViewModel", "wizardViewModel"],
        // Elements to bind to, e.g. #settings_plugin_celestrius, #tab_plugin_celestrius, ...
        elements: [
            "#settings_plugin_celestrius",
            "#wizard_plugin_celestrius",
            "#navbar_plugin_celestrius",
        ],
    });
});
