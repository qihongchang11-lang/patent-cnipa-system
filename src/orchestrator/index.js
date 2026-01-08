const PatentOrchestrator = require('./core/orchestrator');
const JobCardManager = require('./core/jobcard-manager');
const PatentValidator = require('../checks/patent-validator');
const logger = require('../utils/logger');
const config = require('../../config/default.json');

class CnipaPatentSystem {
    constructor() {
        this.orchestrator = new PatentOrchestrator();
        this.jobCardManager = new JobCardManager();
        this.validator = new PatentValidator();
        this.isRunning = false;
    }

    async start() {
        logger.info('Starting CNIPA Patent System...');

        try {
            // Initialize core components
            await this.orchestrator.initialize();
            await this.jobCardManager.initialize();

            // Load and validate job cards
            await this.loadJobCards();

            // Setup input monitoring
            this.setupInputMonitoring();

            this.isRunning = true;
            logger.info('CNIPA Patent System started successfully');

        } catch (error) {
            logger.error('Failed to start CNIPA Patent System:', error);
            throw error;
        }
    }

    async loadJobCards() {
        logger.info('Loading job cards...');

        const jobCards = [
            'patent-application-processing',
            'patent-validation-checklist'
        ];

        for (const cardId of jobCards) {
            try {
                const jobCard = await this.jobCardManager.loadJobCard(cardId);
                logger.info(`Job card loaded: ${cardId} (version ${jobCard.version})`);
            } catch (error) {
                logger.error(`Failed to load job card ${cardId}:`, error);
                throw error;
            }
        }
    }

    setupInputMonitoring() {
        logger.info('Setting up input monitoring...');

        // Monitor data/drafts directory for new applications
        const chokidar = require('chokidar');
        const watcher = chokidar.watch('./data/drafts', {
            ignored: /(^|[\/\])\../, // ignore dotfiles
            persistent: true
        });

        watcher.on('add', async (filePath) => {
            logger.info(`New application detected: ${filePath}`);
            await this.processApplication(filePath);
        });

        watcher.on('error', error => {
            logger.error('File watcher error:', error);
        });

        logger.info('Input monitoring setup complete');
    }

    async processApplication(filePath) {
        try {
            logger.info(`Processing patent application: ${filePath}`);

            // Load application data
            const applicationData = await this.loadApplicationData(filePath);

            // Validate application
            const validationResult = await this.validator.validateApplication(applicationData);
            if (!validationResult.valid) {
                logger.error(`Application validation failed: ${validationResult.errors.join(', ')}`);
                await this.handleValidationFailure(filePath, validationResult);
                return;
            }

            // Start orchestration
            const result = await this.orchestrator.processApplication(applicationData);

            logger.info(`Patent application processed successfully: ${filePath}`);
            return result;

        } catch (error) {
            logger.error(`Failed to process application ${filePath}:`, error);
            await this.handleProcessingFailure(filePath, error);
            throw error;
        }
    }

    async loadApplicationData(filePath) {
        const fs = require('fs').promises;
        const path = require('path');
        const content = await fs.readFile(filePath, 'utf8');

        const ext = path.extname(filePath).toLowerCase();

        switch (ext) {
            case '.json':
                return JSON.parse(content);
            case '.xml':
                return await this.parseXML(content);
            case '.yaml':
            case '.yml':
                const yaml = require('js-yaml');
                return yaml.load(content);
            default:
                throw new Error(`Unsupported file format: ${ext}`);
        }
    }

    async parseXML(xmlContent) {
        const xml2js = require('xml2js');
        const parser = new xml2js.Parser();

        return new Promise((resolve, reject) => {
            parser.parseString(xmlContent, (err, result) => {
                if (err) reject(err);
                else resolve(result);
            });
        });
    }

    async handleValidationFailure(filePath, validationResult) {
        logger.error(`Validation failed for ${filePath}:`, validationResult.errors);
        // Move to error directory
        const fs = require('fs').promises
        const path = require('path');
        const errorDir = './data/errors';
        const filename = path.basename(filePath);

        await fs.mkdir(errorDir, { recursive: true });
        await fs.rename(filePath, path.join(errorDir, filename));

        // Generate validation report
        const validationReport = {
            timestamp: new Date().toISOString(),
            file: filePath,
            errors: validationResult.errors,
            recommendations: validationResult.recommendations
        };

        await fs.writeFile(
            path.join(errorDir, `${filename}.validation-report.json`),
            JSON.stringify(validationReport, null, 2)
        );
    }

    async handleProcessingFailure(filePath, error) {
        logger.error(`Processing failed for ${filePath}:`, error);
        // Implementation for handling processing failures
        // Could include retry logic, notification, etc.
    }

    async stop() {
        logger.info('Stopping CNIPA Patent System...');
        this.isRunning = false;
        // Add cleanup logic here
        logger.info('CNIPA Patent System stopped');
    }
}

// Start the system if run directly
if (require.main === module) {
    const system = new CnipaPatentSystem();

    system.start().catch(error => {
        logger.error('Failed to start system:', error);
        process.exit(1);
    });

    // Handle graceful shutdown
    process.on('SIGINT', () => {
        logger.info('Received SIGINT, shutting down gracefully...');
        system.stop().then(() => {
            process.exit(0);
        });
    });

    process.on('SIGTERM', () => {
        logger.info('Received SIGTERM, shutting down gracefully...');
        system.stop().then(() => {
            process.exit(0);
        });
    });
}

module.exports = CnipaPatentSystem;