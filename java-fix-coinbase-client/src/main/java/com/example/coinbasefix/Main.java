package com.example.coinbasefix;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import quickfix.*;

import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;

/**
 * Main entry point for the Coinbase FIX Client application.
 * Initializes configuration, sets up QuickFIX/J, and starts the initiator.
 */
public class Main {

    private static final Logger log = LoggerFactory.getLogger(Main.class);
    // Used to keep the main thread alive while the FIX session runs in background threads.
    private static final CountDownLatch shutdownLatch = new CountDownLatch(1);
    private static SocketInitiator initiator = null;
    private static final String PROPERTIES_FILE = "coinbase.properties";
    private static final String QUICKFIX_CONFIG_FILE = "quickfix.cfg";


    public static void main(String[] args) {
        log.info("Starting Coinbase FIX Client Application...");

        try {
            // 1. Load Coinbase-specific credentials and settings
            Properties coinbaseProps = loadCoinbaseProperties();
            validateProperties(coinbaseProps); // Ensure required props are present

            // 2. Load QuickFIX/J engine settings
            // Note: Property substitution not used by SessionSettings constructor in QFJ 2.0.0
            SessionSettings settings = loadQuickFixSettings();

            // 3. Create the QuickFIX/J Application implementation
            Application application = new CoinbaseFixClientApplication(coinbaseProps);

            // 4. Set up message store and log factories
            MessageStoreFactory storeFactory = new FileStoreFactory(settings);

            // Use SLF4JLogFactory based on pom.xml dependencies (slf4j-log4j12)
            // This requires log4j:log4j on the classpath and configuration via
            // log4j.properties or log4j.xml in src/main/resources
            LogFactory logFactory = new SLF4JLogFactory(settings);
            log.info("Using SLF4JLogFactory (expects Log4j 1.2 binding and configuration)");

            // 5. Set up message factory
            MessageFactory messageFactory = new DefaultMessageFactory();

            // 6. Create and configure the SocketInitiator
            initiator = new SocketInitiator(application, storeFactory, settings, logFactory, messageFactory);

            // 7. Add a shutdown hook for graceful termination
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                log.info("Shutdown hook triggered. Stopping FIX initiator...");
                try {
                    if (initiator != null && initiator.isLoggedOn()) {
                        // Stop cleanly, allowing logout etc.
                        initiator.stop(true); // force disconnect after timeout if needed
                    } else if (initiator != null) {
                        // If not logged on, just stop
                        initiator.stop();
                    }
                } catch(Exception e) {
                    log.error("Error during initiator shutdown", e);
                } finally {
                    shutdownLatch.countDown(); // Release the main thread
                    log.info("FIX initiator stopped.");
                }
            }, "QFJ Shutdown Hook"));

            // 8. Start the initiator - this will begin connection attempts
            log.info("Starting FIX Initiator...");
            initiator.start();
            log.info("FIX Initiator started. Session(s) will attempt to connect.");
            log.info("Application running. Press Ctrl+C to initiate shutdown.");

            // 9. Keep the main thread alive until shutdown is signaled
            shutdownLatch.await();

        } catch (ConfigError e) {
            log.error("QuickFIX/J Configuration Error: {}", e.getMessage(), e);
            System.exit(1);
        } catch (FileNotFoundException e) {
            log.error("Configuration file not found: {}", e.getMessage());
            System.exit(1);
        } catch (IOException e) {
            log.error("Error reading configuration file: {}", e.getMessage(), e);
            System.exit(1);
        } catch (InterruptedException e) {
            log.error("Application interrupted during startup or wait.", e);
            Thread.currentThread().interrupt(); // Restore interrupt status
            System.exit(1);
        } catch (Exception e) { // Catch any other unexpected exceptions
            log.error("An unexpected error occurred during initialization or runtime: {}", e.getMessage(), e);
            System.exit(1);
        } finally {
             log.info("Application exiting.");
        }
    }

    /**
     * Loads Coinbase-specific properties from the coinbase.properties file.
     *
     * @return Properties object containing the configuration.
     * @throws IOException if the file cannot be read.
     * @throws FileNotFoundException if the file doesn't exist.
     */
    private static Properties loadCoinbaseProperties() throws IOException, FileNotFoundException {
        Properties props = new Properties();
        InputStream inputStream = null;

        // Try loading from classpath first
        inputStream = Main.class.getClassLoader().getResourceAsStream(PROPERTIES_FILE);

        if (inputStream == null) {
            // Try loading from filesystem if not found in classpath
            log.warn("{} not found in classpath, attempting filesystem load.", PROPERTIES_FILE);
            try {
                inputStream = new FileInputStream(PROPERTIES_FILE);
            } catch (FileNotFoundException e) {
                 // Log specific error and re-throw
                 log.error("{} not found in classpath or filesystem. Cannot load required credentials.", PROPERTIES_FILE);
                 throw e;
            }
        }

        try {
            props.load(inputStream);
            log.info("Loaded Coinbase configuration from {}", PROPERTIES_FILE);
        } finally {
            if (inputStream != null) {
                try {
                    inputStream.close();
                } catch (IOException e) {
                    log.warn("Failed to close input stream for {}", PROPERTIES_FILE, e);
                }
            }
        }
        return props;
    }

     /**
      * Validates that essential Coinbase properties are present and not placeholders.
      * Throws IllegalArgumentException if validation fails.
      *
      * @param props The properties loaded from coinbase.properties.
      */
     private static void validateProperties(Properties props) {
        String[] requiredKeys = {
            "coinbase.fix.senderCompId",
            "coinbase.fix.username",
            "coinbase.fix.passphrase",
            "coinbase.fix.secretKey",
            "coinbase.fix.targetCompId",
            "coinbase.fix.host",
            "coinbase.fix.port",
            "coinbase.fix.fixVersion",
            "coinbase.fix.defaultApplVerId",
            "coinbase.fix.subscribe.products"
            // Add other *critical* properties here if needed
        };

        boolean missing = false;
        StringBuilder missingKeys = new StringBuilder();
        for (String key : requiredKeys) {
            String value = props.getProperty(key);
            if (value == null || value.trim().isEmpty() || value.contains("YOUR_")) {
                 log.error("Missing or placeholder configuration value for required property: {}", key);
                 if (missing) missingKeys.append(", ");
                 missingKeys.append(key);
                 missing = true;
            }
        }
         if (missing) {
             throw new IllegalArgumentException("One or more required properties are missing or incomplete in "
                     + PROPERTIES_FILE + ": [" + missingKeys.toString() + "]");
         }
         log.info("Coinbase properties validated successfully.");
     }

    /**
     * Loads QuickFIX/J session settings from the quickfix.cfg file.
     * Uses the constructor compatible with QFJ 2.0.0.
     *
     * @return SessionSettings object.
     * @throws IOException if the file cannot be read.
     * @throws ConfigError if the QuickFIX/J configuration is invalid.
     * @throws FileNotFoundException if the file doesn't exist.
     */
    private static SessionSettings loadQuickFixSettings() throws IOException, ConfigError, FileNotFoundException {
         InputStream inputStream = null;
         // Try loading quickfix.cfg from classpath
         inputStream = Main.class.getClassLoader().getResourceAsStream(QUICKFIX_CONFIG_FILE);

         if (inputStream == null) {
             // Try loading from filesystem if not found in classpath
             log.warn("{} not found in classpath, attempting filesystem load.", QUICKFIX_CONFIG_FILE);
             try {
                 inputStream = new FileInputStream(QUICKFIX_CONFIG_FILE);
             } catch (FileNotFoundException e) {
                 log.error("{} not found in classpath or filesystem. Cannot load QuickFIX/J settings.", QUICKFIX_CONFIG_FILE);
                 throw e;
             }
         }

         try {
             // Use the constructor available in QFJ 2.0.0 (takes only InputStream)
             SessionSettings settings = new SessionSettings(inputStream);
             log.info("Loaded QuickFIX/J configuration from {}", QUICKFIX_CONFIG_FILE);
             return settings;
         } finally {
             if(inputStream != null) {
                 try {
                     inputStream.close();
                 } catch (IOException e) {
                      log.warn("Failed to close input stream for {}", QUICKFIX_CONFIG_FILE, e);
                 }
             }
         }
    }
}