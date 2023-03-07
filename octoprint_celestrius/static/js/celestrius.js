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

        self.isEnabled = ko.pureComputed(function() {
            return self.settingsViewModel.settings.plugins.celestrius.enabled
                && self.settingsViewModel.settings.plugins.celestrius.enabled();
        })

        // TODO: Implement your plugin's view model here.
        self.toggleIsEnabled = function () {
            const newVal = !self.settingsViewModel.settings.plugins.celestrius.enabled();
            self.settingsViewModel.settings.plugins.celestrius.enabled(newVal);
            self.settingsViewModel.saveData();
        };
        self.navbarButtonTitle = ko.pureComputed(function () {
            return self.settingsViewModel.settings.plugins.celestrius.enabled()
                ? "Celetrius is collecting data. Click to turn OFF."
                : "Celetrius is NOT collecting data. Click to turn ON.";
        });

        self.termsAccepted = ko.pureComputed(function () {
            return self.settingsViewModel.settings.plugins.celestrius.terms_accepted();
        });
        self.consentText = ko.pureComputed(function () {
            return self.termsAccepted()
                ? "You accepted the terms for participating in the pilot program."
                : "I understand the privacy policy and accept the terms for participating in the pilot program."
        });
        self.savePluginSettings = function () {
            self.settingsViewModel.saveData();
            return true;
        }
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
        elements: ["#settings_plugin_celestrius", '#wizard_plugin_celestrius', "#navbar_plugin_celestrius"],
    });
});
