#!/usr/bin/env node

const fs = require('fs').promises;
const path = require('path');
const JobCardManager = require('../src/core/jobcard-manager');
const logger = require('../src/utils/logger');

async function validateJobCard(filePath) {
    try {
        console.log(`Validating job card: ${filePath}`);

        // Check if file exists
        try {
            await fs.access(filePath);
        } catch (error) {
            console.error(`File not found: ${filePath}`);
            process.exit(1);
        }

        // Load job card data
        const content = await fs.readFile(filePath, 'utf8');
        const jobCardData = JSON.parse(content);

        // Create job card manager and validator
        const jobCardManager = new JobCardManager();
        const validationResult = await jobCardManager.validateJobCard(jobCardData);

        // Display results
        console.log('\n=== Job Card Validation Results ===');
        console.log(`Valid: ${validationResult.valid}`);
        console.log(`Job Card Name: ${jobCardData.name}`);
        console.log(`Version: ${jobCardData.version}`);
        console.log(`Type: ${jobCardData.type || 'workflow'}`);

        if (validationResult.errors.length > 0) {
            console.log('\nErrors:');
            validationResult.errors.forEach((error, index) => {
                console.log(`  ${index + 1}. ${error}`);
            });
        }

        if (validationResult.warnings && validationResult.warnings.length > 0) {
            console.log('\nWarnings:');
            validationResult.warnings.forEach((warning, index) => {
                console.log(`  ${index + 1}. ${warning}`);
            });
        }

        if (validationResult.recommendations && validationResult.recommendations.length > 0) {
            console.log('\nRecommendations:');
            validationResult.recommendations.forEach((recommendation, index) => {
                console.log(`  ${index + 1}. ${recommendation}`);
            });
        }

        // Step validation
        if (jobCardData.steps && jobCardData.steps.length > 0) {
            console.log(`\nWorkflow Analysis:`);
            console.log(`  Total Steps: ${jobCardData.steps.length}`);

            const stepTypes = {};
            jobCardData.steps.forEach(step => {
                stepTypes[step.type] = (stepTypes[step.type] || 0) + 1;
            });

            console.log(`  Step Types:`);
            Object.entries(stepTypes).forEach(([type, count]) => {
                console.log(`    ${type}: ${count}`);
            });

            // Check for workflow completeness
            const stepIds = jobCardData.steps.map(step => step.id);
            const referencedSteps = new Set();

            jobCardData.steps.forEach(step => {
                if (step.next) {
                    step.next.forEach(nextStep => {
                        referencedSteps.add(nextStep);
                    });
                }
            });

            const orphanedSteps = Array.from(referencedSteps).filter(stepId =>
                !stepIds.includes(stepId)
            );

            if (orphanedSteps.length > 0) {
                console.log(`  Orphaned References: ${orphanedSteps.join(', ')}`);
                warnings.push(`Steps reference non-existent steps: ${orphanedSteps.join(', ')}`);
            }
        }

        // Performance analysis
        if (jobCardData.performance) {
            console.log(`\nPerformance Settings:`);
            console.log(`  Timeout: ${jobCardData.performance.timeout || 'none'}`);
            console.log(`  Priority: ${jobCardData.performance.priority || 'normal'}`);
            console.log(`  Parallel Processing: ${jobCardData.performance.parallelProcessing ? 'yes' : 'no'}`);
            if (jobCardData.performance.parallelProcessing) {
                console.log(`  Max Concurrent: ${jobCardData.performance.maxConcurrentSteps || 'auto'}`);
            }
        }

        // Error handling analysis
        if (jobCardData.errorHandling) {
            console.log(`\nError Handling:`);
            if (jobCardData.errorHandling.retryPolicy) {
                console.log(`  Max Retries: ${jobCardData.errorHandling.retryPolicy.maxRetries}`);
                console.log(`  Retry Strategy: ${jobCardData.errorHandling.retryPolicy.retryDelay}`);
            }
            if (jobCardData.errorHandling.escalation) {
                console.log(`  Escalation: ${jobCardData.errorHandling.escalation.enabled ? 'yes' : 'no'}`);
            }
        }

        // Generate detailed report
        if (process.argv.includes('--detailed')) {
            await generateDetailedReport(filePath, jobCardData, validationResult);
        }

        process.exit(validationResult.valid ? 0 : 1);

    } catch (error) {
        console.error('Job card validation failed:', error.message);
        logger.error('Job card validation error:', error);
        process.exit(1);
    }
}

async function generateDetailedReport(filePath, jobCardData, validationResult) {
    const report = {
        timestamp: new Date().toISOString(),
        file: filePath,
        jobCard: {
            id: jobCardData.id,
            name: jobCardData.name,
            version: jobCardData.version,
            type: jobCardData.type,
            description: jobCardData.description
        },
        workflow: {
            totalSteps: jobCardData.steps?.length || 0,
            stepList: jobCardData.steps?.map(step => ({
                id: step.id,
                name: step.name,
                type: step.type,
                timeout: step.timeout
            })) || []
        },
        validation: validationResult,
        summary: {
            totalErrors: validationResult.errors.length,
            totalWarnings: validationResult.warnings?.length || 0,
            totalRecommendations: validationResult.recommendations?.length || 0,
            status: validationResult.valid ? 'VALID' : 'INVALID'
        }
    };

    const reportFile = `${filePath}.validation-report.json`;
    await fs.writeFile(reportFile, JSON.stringify(report, null, 2));

    console.log(`\nDetailed validation report saved to: ${reportFile}`);
}

// Main execution
if (require.main === module) {
    const filePath = process.argv[2];

    if (!filePath) {
        console.error('Usage: node validate-jobcard.js <job-card-file> [--detailed]');
        process.exit(1);
    }

    validateJobCard(filePath);
}

module.exports = { validateJobCard };