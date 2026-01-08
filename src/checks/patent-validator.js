const Ajv = require('ajv');
const addFormats = require('ajv-formats');
const logger = require('../utils/logger');

class PatentValidator {
    constructor() {
        this.ajv = new Ajv({ allErrors: true, verbose: true });
        addFormats(this.ajv);
        this.schemas = {};
        this.loadSchemas();
    }

    async loadSchemas() {
        try {
            // Load patent application schema
            const patentSchema = require('../../schema/patent-application-v1.0.json');
            this.ajv.addSchema(patentSchema, 'patent-application');
            this.schemas['patent-application'] = patentSchema;

            // Load job card schema
            const jobCardSchema = require('../../schema/job-card-v1.0.json');
            this.ajv.addSchema(jobCardSchema, 'job-card');
            this.schemas['job-card'] = jobCardSchema;

            logger.info('Schemas loaded successfully');
        } catch (error) {
            logger.error('Failed to load schemas:', error);
            throw error;
        }
    }

    async validateApplication(applicationData, options = {}) {
        const { strict = true } = options;

        try {
            logger.info('Validating patent application...');

            // Schema validation
            const schemaValidation = await this.validateSchema(applicationData);
            if (!schemaValidation.valid) {
                return schemaValidation;
            }

            // Business rule validation
            const businessValidation = await this.validateBusinessRules(applicationData);
            if (!businessValidation.valid) {
                return businessValidation;
            }

            // CNIPA specific validation
            const cnipaValidation = await this.validateCnipaRequirements(applicationData);

            logger.info('Patent application validation completed');
            return this.combineValidationResults([schemaValidation, businessValidation, cnipaValidation]);

        } catch (error) {
            logger.error('Validation error:', error);
            return {
                valid: false,
                errors: [`Validation error: ${error.message}`],
                recommendations: []
            };
        }
    }

    async validateSchema(data) {
        try {
            const validate = this.ajv.getSchema('patent-application');
            if (!validate) {
                throw new Error('Patent application schema not found');
            }

            const valid = validate(data);

            if (!valid) {
                const errors = validate.errors.map(error => {
                    return `${error.instancePath || 'root'}: ${error.message}`;
                });

                return {
                    valid: false,
                    errors,
                    recommendations: this.generateSchemaRepairRecommendations(validate.errors)
                };
            }

            return {
                valid: true,
                errors: [],
                recommendations: []
            };

        } catch (error) {
            return {
                valid: false,
                errors: [`Schema validation error: ${error.message}`],
                recommendations: []
            };
        }
    }

    async validateBusinessRules(applicationData) {
        const errors = [];
        const recommendations = [];

        try {
            // Check filing date consistency
            if (applicationData.filing_date && applicationData.priority_claims) {
                const filingDate = new Date(applicationData.filing_date);
                applicationData.priority_claims.forEach(priority => {
                    const priorityDate = new Date(priority.priority_date);
                    if (priorityDate >= filingDate) {
                        errors.push(`Priority date ${priority.priority_date} must be before filing date ${applicationData.filing_date}`);
                    }
                });
            }

            // Check claim format and dependency
            if (applicationData.claims && applicationData.claims.length > 0) {
                const dependencyErrors = this.validateClaimDependency(applicationData.claims);
                errors.push(...dependencyErrors);
            }

            // Check application number format
            if (applicationData.application_number) {
                if (!this.isValidApplicationNumber(applicationData.application_number)) {
                    errors.push(`Invalid CNIPA application number format: ${applicationData.application_number}`);
                }
            }

            // Check classification codes
            if (applicationData.classification && applicationData.classification.ipc) {
                const ipcErrors = this.validateIPCClassification(applicationData.classification.ipc);
                errors.push(...ipcErrors);
            }

            if (errors.length > 0) {
                return {
                    valid: false,
                    errors,
                    recommendations
                };
            }

            return {
                valid: true,
                errors: [],
                recommendations
            };

        } catch (error) {
            return {
                valid: false,
                errors: [`Business rule validation error: ${error.message}`],
                recommendations: []
            };
        }
    }

    async validateCnipaRequirements(applicationData) {
        const errors = [];
        const warnings = [];

        try {
            // CNIPA specific format requirements
            const formatErrors = this.validateFormatRequirements(applicationData);
            errors.push(...formatErrors);

            // Language requirements
            if (applicationData.language && !['zh-CN', 'en', 'ja', 'de', 'fr'].includes(applicationData.language)) {
                if (applicationData.language === 'other') {
                    warnings.push('Foreign language applications require Chinese translation');
                }
            }

            // Drawing requirements
            if (applicationData.drawings && applicationData.drawings.length > 0) {
                const drawingErrors = this.validateDrawingRequirements(applicationData.drawings);
                errors.push(...drawingErrors);
            }

            // Sequence listing requirements for biotech applications
            if (this.hasBiotechnologyContent(applicationData)) {
                if (!applicationData.sequence_listing) {
                    warnings.push('Sequence listing is recommended for biotechnology applications');
                }
            }

            return {
                valid: errors.length === 0,
                errors,
                warnings,
                recommendations: this.generateCnipaRecommendations(errors, warnings)
            };

        } catch (error) {
            return {
                valid: false,
                errors: [`CNIPA requirement validation error: ${error.message}`],
                recommendations: []
            };
        }
    }

    validateClaimDependency(claims) {
        const errors = [];

        for (let i = 0; i < claims.length; i++) {
            const claim = claims[i];

            if (claim.claim_type === 'dependent' && !this.hasClaimReference(claim.claim_text)) {
                errors.push(`Dependent claim ${claim.claim_number} must reference another claim`);
            }

            if (claim.claim_type === 'multiple_dependent' && !this.isValidMultipleDependentReference(claim)) {
                errors.push(`Multiple dependent claim ${claim.claim_number} has invalid reference format`);
            }
        }

        return errors;
    }

    hasClaimReference(claimText) {
        // Check if claim references another claim (e.g., "Claim 1", "The method of claim 2", etc.)
        return /claim\s+\d+/i.test(claimText);
    }

    isValidMultipleDependentReference(claim) {
        // Check for proper multiple dependent claim format
        const text = claim.claim_text.toLowerCase();
        return /claims?\s+(\d+(?:\s*,\s*\d+)*)|any\s+of\s+claims?\s+/i.test(text);
    }

    isValidApplicationNumber(appNumber) {
        // CNIPA application number format: 20231123456789 (14 digits)
        return /^\d{14}$/.test(appNumber);
    }

    validateIPCClassification(ipcCodes) {
        const errors = [];
        const ipcPattern = /^[A-H]\d{1,2}[A-Z] \d{1,4}\/\d{2,4}$/;

        ipcCodes.forEach(code => {
            if (!ipcPattern.test(code)) {
                errors.push(`Invalid IPC classification format: ${code}. Expected format: A01B 1/00`);
            }
        });

        return errors;
    }

    validateFormatRequirements(data) {
        const errors = [];

        // Specification format requirements
        if (data.specification && data.specification.description) {
            if (data.specification.description.length < 500) {
                errors.push('Specification description must contain sufficient detail (minimum 500 characters)');
            }
        }

        // Title requirements
        if (data.title && data.title.length < 10) {
            errors.push('Title must be descriptive (minimum 10 characters)');
        }

        // Abstract requirements
        if (data.abstract) {
            if (data.abstract.length > 1000) {
                errors.push('Abstract exceeds maximum length (1000 characters)');
            }
            if (data.abstract.length < 50) {
                errors.push('Abstract too brief (minimum 50 characters)');
            }
        }

        return errors;
    }

    validateDrawingRequirements(drawings) {
        const errors = [];

        drawings.forEach((drawing, index) => {
            if (!drawing.description || drawing.description.length < 10) {
                errors.push(`Drawing ${drawing.drawing_number || index + 1} requires adequate description`);
            }

            if (!drawing.file_reference) {
                errors.push(`Drawing ${drawing.drawing_number || index + 1} must have file reference`);
            }
        });

        return errors;
    }

    hasBiotechnologyContent(data) {
        // Simple heuristic to detect potential biotech content
        if (!data.specification || !data.specification.description) {
            return false;
        }

        const biotechKeywords = [
            'gene', 'dna', 'rna', 'protein', 'enzyme', 'cell', 'organism',
            'biotechnology', 'bioengineering', 'genetic engineering',
            'protein engineering', 'immunology', 'pharmaceutical'
        ];

        const description = data.specification.description.toLowerCase();
        return biotechKeywords.some(keyword => description.includes(keyword));
    }

    generateSchemaRepairRecommendations(schemaErrors) {
        const recommendations = [];

        schemaErrors.forEach(error => {
            if (error.keyword === 'required') {
                recommendations.push(`Add missing required field: ${error.params.missingProperty}`);
            }
            if (error.keyword === 'type') {
                recommendations.push(`Correct data type for ${error.instancePath}: expected ${error.params.type}`);
            }
            if (error.keyword === 'format') {
                recommendations.push(`Change format of ${error.instancePath} to ${error.params.format}`);
            }
        });

        return recommendations;
    }

    generateCnipaRecommendations(errors, warnings) {
        const recommendations = [];

        if (warnings.some(w => w.includes('translation'))) {
            recommendations.push('Consider providing Chinese translation for foreign language content');
        }

        if (warnings.some(w => w.includes('sequence listing'))) {
            recommendations.push('Provide sequence listing in standard ST.25 format for biotechnology applications');
        }

        if (errors.some(e => e.includes('specification'))) {
            recommendations.push('Review CNIPA specification guidelines for proper format and content');
        }

        return recommendations;
    }

    combineValidationResults(results) {
        const combined = {
            valid: true,
            errors: [],
            warnings: [],
            recommendations: []
        };

        results.forEach(result => {
            combined.valid = combined.valid && result.valid;
            combined.errors.push(...(result.errors || []));
            combined.warnings.push(...(result.warnings || []));
            combined.recommendations.push(...(result.recommendations || []));
        });

        return combined;
    }

    async validateJobCard(jobCardData) {
        try {
            const validate = this.ajv.getSchema('job-card');
            if (!validate) {
                throw new Error('Job card schema not found');
            }

            const valid = validate(jobCardData);

            if (!valid) {
                const errors = validate.errors.map(error => {
                    return `${error.instancePath || 'root'}: ${error.message}`;
                });

                return {
                    valid: false,
                    errors,
                    recommendations: this.generateSchemaRepairRecommendations(validate.errors)
                };
            }

            return {
                valid: true,
                errors: [],
                recommendations: []
            };

        } catch (error) {
            return {
                valid: false,
                errors: [`Job card validation error: ${error.message}`],
                recommendations: []
            };
        }
    }
}

module.exports = PatentValidator;